package dev.finrag.gateway.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import dev.finrag.gateway.accounting.UsageAccounting;
import dev.finrag.gateway.api.Dtos.EmbeddingRequest;
import dev.finrag.gateway.audit.AuditLog;
import dev.finrag.gateway.audit.AuditRecord;
import dev.finrag.gateway.cache.ResponseCache;
import dev.finrag.gateway.config.GatewayProperties;
import dev.finrag.gateway.config.GatewayProperties.ModelKind;
import dev.finrag.gateway.provider.ModelProvider;
import dev.finrag.gateway.provider.ProviderException;
import dev.finrag.gateway.provider.ProviderRegistry;
import dev.finrag.gateway.resilience.ResilientCaller;
import dev.finrag.gateway.routing.ModelRouter;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import tools.jackson.databind.json.JsonMapper;

/** Retries, circuit breaking and fallback across providers, with fake providers instead of HTTP. */
class ResilienceAndFallbackTests {

    /** Fails with the given exception (if any) and counts how often it was called. */
    static final class FakeProvider implements ModelProvider {
        final String name;
        final AtomicInteger calls = new AtomicInteger();
        ProviderException failure;

        FakeProvider(String name, ProviderException failure) {
            this.name = name;
            this.failure = failure;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public EmbedResult embed(String upstreamModel, List<String> input, String requestId) {
            calls.incrementAndGet();
            if (failure != null) {
                throw failure;
            }
            return new EmbedResult(List.of(new float[] { 1f }), 7);
        }
    }

    FakeProvider primary;
    FakeProvider backup;
    AuditLog audit;
    GatewayService service;
    ResilientCaller caller;

    @BeforeEach
    void setUp() {
        primary = new FakeProvider("primary", null);
        backup = new FakeProvider("backup", null);
        GatewayProperties.Model model = new GatewayProperties.Model(ModelKind.EMBEDDING, "primary", "m-primary",
                List.of(new GatewayProperties.Target("backup", "m-backup")), null, null);
        GatewayProperties props = new GatewayProperties(List.of(), Map.of(), Map.of("emb", model), null,
                new GatewayProperties.Cache(false, Duration.ofMinutes(1), 16),
                new GatewayProperties.Resilience(3, Duration.ofMillis(1), 50, 10, Duration.ofMinutes(5)));
        ProviderRegistry registry = mock(ProviderRegistry.class);
        when(registry.get("primary")).thenReturn(Optional.of(primary));
        when(registry.get("backup")).thenReturn(Optional.of(backup));
        audit = mock(AuditLog.class);
        caller = new ResilientCaller(props);
        ResponseCache cache = mock(ResponseCache.class);
        when(cache.key(any(), any())).thenReturn("k");
        when(cache.get(any(), any())).thenReturn(Optional.empty());
        when(cache.maxEmbeddingInputs()).thenReturn(16);
        service = new GatewayService(new ModelRouter(props, registry), caller, cache,
                new UsageAccounting(new SimpleMeterRegistry()), audit, JsonMapper.builder().build());
    }

    private EmbeddingRequest request() {
        return new EmbeddingRequest("emb", List.of("hello"));
    }

    @Test
    void retryableFailureIsRetriedThenFallsBack() {
        primary.failure = new ProviderException("primary", "upstream HTTP 503", true, null);
        var resp = service.embed(request(), "r1", "client");
        assertThat(resp.provider()).isEqualTo("backup");
        assertThat(primary.calls.get()).isEqualTo(3); // retry-attempts
        ArgumentCaptor<AuditRecord> rec = ArgumentCaptor.forClass(AuditRecord.class);
        verify(audit).record(rec.capture());
        assertThat(rec.getValue().fallbackUsed()).isTrue();
        assertThat(rec.getValue().attempts()).isEqualTo(4);
        assertThat(rec.getValue().provider()).isEqualTo("backup");
    }

    @Test
    void clientErrorIsNeitherRetriedNorFallenBack() {
        primary.failure = new ProviderException("primary", "upstream HTTP 400", false, null);
        assertThatThrownBy(() -> service.embed(request(), "r2", "client")).isInstanceOf(ProviderException.class);
        assertThat(primary.calls.get()).isEqualTo(1);
        assertThat(backup.calls.get()).isZero();
        ArgumentCaptor<AuditRecord> rec = ArgumentCaptor.forClass(AuditRecord.class);
        verify(audit).record(rec.capture());
        assertThat(rec.getValue().outcome()).isEqualTo("error");
    }

    @Test
    void openCircuitSkipsThePrimaryEntirely() {
        primary.failure = new ProviderException("primary", "upstream unreachable or timed out", true, null);
        for (int i = 0; i < 3; i++) {
            service.embed(request(), "r" + i, "client"); // 3 requests x 3 attempts = 9 recorded failures
        }
        assertThat(caller.state("primary")).isEqualTo(CircuitBreaker.State.OPEN);
        int before = primary.calls.get();
        var resp = service.embed(request(), "r-open", "client");
        assertThat(resp.provider()).isEqualTo("backup");
        assertThat(primary.calls.get()).isEqualTo(before); // rejected without a network call
    }

    @Test
    void costIsComputedPerThousandTokens() {
        GatewayProperties.Model priced = new GatewayProperties.Model(ModelKind.CHAT, "p", "u", null,
                new BigDecimal("0.15"), new BigDecimal("0.60"));
        assertThat(UsageAccounting.cost(priced, 2000, 500)).isEqualByComparingTo("0.6");
        verify(audit, never()).record(any());
    }
}
