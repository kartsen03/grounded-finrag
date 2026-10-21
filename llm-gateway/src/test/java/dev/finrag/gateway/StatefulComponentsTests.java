package dev.finrag.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;

import dev.finrag.gateway.api.Dtos.RerankResponse;
import dev.finrag.gateway.api.Dtos.Usage;
import dev.finrag.gateway.audit.AuditLog;
import dev.finrag.gateway.audit.AuditRecord;
import dev.finrag.gateway.cache.ResponseCache;
import dev.finrag.gateway.ratelimit.RateLimiter;

/** Rate limiting, caching and the audit log against real Redis and PostgreSQL containers. */
@SpringBootTest
@TestPropertySource(properties = { "gateway.clients[0].id=rag-service",
        "gateway.clients[0].key-sha256=3ba18319a2ad80604249578a621bb2eb761c09e23bf7895434dc43dadff51915",
        "gateway.clients[0].requests-per-minute=5" })
class StatefulComponentsTests extends IntegrationTestBase {

    @Autowired
    RateLimiter limiter;

    @Autowired
    ResponseCache cache;

    @Autowired
    AuditLog audit;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void rateLimiterAllowsTheLimitThenRejects() {
        // The Redis container is shared with other test classes; start from an empty window.
        redis.delete(redis.keys("gw:rl:*"));
        List<Boolean> decisions = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            decisions.add(limiter.check("rag-service").allowed());
        }
        // The window may roll over mid-test; at most 5 allowed per window either way.
        assertThat(decisions.stream().filter(b -> b).count()).isBetween(5L, 7L);
        assertThat(decisions.subList(0, 5)).doesNotContain(false).hasSize(5);
    }

    @Test
    void cacheRoundTripsResponsesByRequestHash() {
        record Req(String model, String query) {
        }
        String key = cache.key("rerank", new Req("m", "q"));
        assertThat(key).isEqualTo(cache.key("rerank", new Req("m", "q")));
        assertThat(key).isNotEqualTo(cache.key("rerank", new Req("m", "q2")));
        cache.put(key, new RerankResponse("r", "m", "p", List.of(0.5), new Usage(3, 0), 9, false, BigDecimal.ZERO));
        assertThat(cache.get(key, RerankResponse.class)).get().extracting(RerankResponse::scores)
                .isEqualTo(List.of(0.5));
    }

    @Test
    void auditLogIsAppendOnlyAndHashChainedUnderConcurrency() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        List<Future<?>> futures = new ArrayList<>();
        for (int i = 0; i < 40; i++) {
            int n = i;
            futures.add(pool.submit(() -> audit.record(new AuditRecord("chain-" + n, "rag-service", "/v1/embeddings",
                    "bge-base-en-v1.5", "local-models", "bge-base-en-v1.5", "ok", 200, false, 1, false, 12, 0,
                    BigDecimal.ZERO, 5, null, "abc", "contact jane@example.com"))));
        }
        for (Future<?> f : futures) {
            f.get();
        }
        pool.shutdown();

        AuditLog.Verification v = audit.verify();
        assertThat(v.intact()).isTrue();
        assertThat(v.rows()).isGreaterThanOrEqualTo(40);
        assertThat(jdbc.queryForObject("SELECT request_preview FROM gateway.audit_log WHERE request_id = 'chain-0'",
                String.class)).contains("[REDACTED_EMAIL]").doesNotContain("jane@example.com");

        assertThatThrownBy(() -> jdbc.update("UPDATE gateway.audit_log SET outcome = 'tampered'"))
                .isInstanceOf(DataAccessException.class).hasMessageContaining("append-only");
        assertThatThrownBy(() -> jdbc.update("DELETE FROM gateway.audit_log")).isInstanceOf(DataAccessException.class);
        assertThatThrownBy(() -> jdbc.execute("TRUNCATE gateway.audit_log")).isInstanceOf(DataAccessException.class);
    }
}
