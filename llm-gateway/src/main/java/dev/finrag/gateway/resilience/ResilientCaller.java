package dev.finrag.gateway.resilience;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;
import dev.finrag.gateway.provider.ProviderException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.core.IntervalFunction;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;

/**
 * Wraps each provider call in a retry (outer) around a circuit breaker (inner), one of each per
 * provider:
 * <ul>
 * <li>Only retryable failures (timeouts, I/O, 429, 5xx) are retried, with exponential backoff.
 * A 4xx means the request itself is wrong, and repeating it cannot help.</li>
 * <li>The breaker counts only retryable failures. When too many recent calls fail it opens and
 * rejects calls immediately for a while, so a dead provider costs nothing per request and the
 * router can fall back at once.</li>
 * </ul>
 */
@Component
public class ResilientCaller {

    private final GatewayProperties.Resilience settings;
    private final Map<String, CircuitBreaker> breakers = new ConcurrentHashMap<>();
    private final Map<String, Retry> retries = new ConcurrentHashMap<>();

    public ResilientCaller(GatewayProperties properties) {
        this.settings = properties.resilience();
    }

    public record Outcome<T>(T value, int attempts) {
    }

    public <T> Outcome<T> call(String provider, Supplier<T> supplier) {
        return call(provider, supplier, new AtomicInteger());
    }

    /** {@code attempts} counts every upstream attempt, including ones that end in failure. */
    public <T> Outcome<T> call(String provider, Supplier<T> supplier, AtomicInteger attempts) {
        int before = attempts.get();
        Supplier<T> counted = () -> {
            attempts.incrementAndGet();
            return supplier.get();
        };
        Supplier<T> guarded = CircuitBreaker.decorateSupplier(breaker(provider), counted);
        T value = Retry.decorateSupplier(retry(provider), guarded).get();
        return new Outcome<>(value, attempts.get() - before);
    }

    public CircuitBreaker.State state(String provider) {
        return breaker(provider).getState();
    }

    public CircuitBreaker breaker(String provider) {
        return breakers.computeIfAbsent(provider, name -> CircuitBreaker.of(name, CircuitBreakerConfig.custom()
                .failureRateThreshold(settings.breakerFailureRatePercent())
                .slidingWindowSize(settings.breakerWindowCalls())
                .minimumNumberOfCalls(Math.min(5, settings.breakerWindowCalls()))
                .waitDurationInOpenState(settings.breakerOpenFor())
                .permittedNumberOfCallsInHalfOpenState(2)
                .recordException(ResilientCaller::retryable)
                .build()));
    }

    private Retry retry(String provider) {
        return retries.computeIfAbsent(provider, name -> Retry.of(name, RetryConfig.custom()
                .maxAttempts(settings.retryAttempts())
                .intervalFunction(IntervalFunction.ofExponentialBackoff(settings.retryWait(), 2.0))
                .retryOnException(e -> retryable(e) && !(e instanceof CallNotPermittedException))
                .build()));
    }

    static boolean retryable(Throwable e) {
        return e instanceof ProviderException p && p.retryable();
    }
}
