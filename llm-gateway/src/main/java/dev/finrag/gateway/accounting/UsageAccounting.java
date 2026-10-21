package dev.finrag.gateway.accounting;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

/**
 * Per-request token, cost and latency accounting, exported as Micrometer metrics
 * (/actuator/metrics, /actuator/prometheus) and written to the audit log by the service.
 * Cost uses the per-1,000-token prices configured on each model alias (0 for local models).
 */
@Component
public class UsageAccounting {

    private final MeterRegistry registry;

    public UsageAccounting(MeterRegistry registry) {
        this.registry = registry;
    }

    public static BigDecimal cost(GatewayProperties.Model model, int promptTokens, int completionTokens) {
        BigDecimal prompt = model.costPer1kPromptUsd().multiply(BigDecimal.valueOf(promptTokens));
        BigDecimal completion = model.costPer1kCompletionUsd().multiply(BigDecimal.valueOf(completionTokens));
        return prompt.add(completion).divide(BigDecimal.valueOf(1000), 8, RoundingMode.HALF_UP);
    }

    public void record(String model, String provider, String client, String outcome, boolean cacheHit,
            int promptTokens, int completionTokens, BigDecimal cost, long latencyMs) {
        String[] tags = { "model", model, "provider", provider == null ? "none" : provider, "client",
                client == null ? "unknown" : client, "outcome", outcome, "cache", String.valueOf(cacheHit) };
        Counter.builder("gateway.requests").tags(tags).register(registry).increment();
        Timer.builder("gateway.request.latency").tags(tags).publishPercentiles(0.5, 0.95).register(registry)
                .record(java.time.Duration.ofMillis(latencyMs));
        Counter.builder("gateway.tokens").tags("model", model, "type", "prompt").register(registry)
                .increment(promptTokens);
        Counter.builder("gateway.tokens").tags("model", model, "type", "completion").register(registry)
                .increment(completionTokens);
        Counter.builder("gateway.cost.usd").tags("model", model).register(registry).increment(cost.doubleValue());
    }
}
