package dev.finrag.gateway.health;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.health.contributor.AbstractHealthIndicator;
import org.springframework.boot.health.contributor.Health;
import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;
import dev.finrag.gateway.resilience.ResilientCaller;

/**
 * /actuator/health detail for upstream providers: reachability of each local provider and the
 * state of its circuit breaker. Hosted providers are not pinged (that would spend quota).
 */
@Component("providers")
public class ProvidersHealthIndicator extends AbstractHealthIndicator {

    private static final Map<GatewayProperties.ProviderType, String> PING = Map.of(
            GatewayProperties.ProviderType.OLLAMA, "/api/version",
            GatewayProperties.ProviderType.MODEL_SERVER, "/health");
    private final GatewayProperties properties;
    private final ResilientCaller caller;
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(1)).build();

    public ProvidersHealthIndicator(GatewayProperties properties, ResilientCaller caller) {
        this.properties = properties;
        this.caller = caller;
    }

    @Override
    protected void doHealthCheck(Health.Builder builder) {
        boolean allUp = true;
        for (var entry : properties.providers().entrySet()) {
            String path = PING.get(entry.getValue().type());
            if (path == null) {
                continue;
            }
            boolean up;
            try {
                HttpRequest req = HttpRequest.newBuilder(URI.create(entry.getValue().baseUrl() + path))
                        .timeout(Duration.ofSeconds(2)).GET().build();
                up = http.send(req, HttpResponse.BodyHandlers.discarding()).statusCode() == 200;
            } catch (Exception e) {
                up = false;
            }
            allUp &= up;
            builder.withDetail(entry.getKey(), Map.of("reachable", up, "circuit", caller.state(entry.getKey()).name()));
        }
        if (allUp) {
            builder.up();
        } else {
            builder.status("DEGRADED");
        }
    }
}
