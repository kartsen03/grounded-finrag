package dev.finrag.gateway.audit;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import dev.finrag.gateway.security.Redactor;

/**
 * Writes the append-only audit log (gateway.audit_log) and verifies its hash chain.
 * The database enforces append-only (UPDATE/DELETE/TRUNCATE raise) and computes the chain in an
 * insert trigger, so even code with database access cannot rewrite history unnoticed.
 */
@Component
public class AuditLog {

    private static final Logger log = LoggerFactory.getLogger(AuditLog.class);
    private static final int PREVIEW_CHARS = 160;
    private final JdbcTemplate jdbc;

    public AuditLog(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void record(AuditRecord r) {
        String preview = r.requestPreview() == null ? null
                : Redactor.redact(r.requestPreview().substring(0, Math.min(PREVIEW_CHARS, r.requestPreview().length())));
        try {
            jdbc.update("""
                    INSERT INTO gateway.audit_log (request_id, client_id, endpoint, model_alias, provider, upstream_model,
                        outcome, http_status, cache_hit, attempts, fallback_used, prompt_tokens, completion_tokens,
                        cost_usd, latency_ms, error_type, request_sha256, request_preview, row_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')""",
                    r.requestId(), r.clientId(), r.endpoint(), r.modelAlias(), r.provider(), r.upstreamModel(),
                    r.outcome(), r.httpStatus(), r.cacheHit(), r.attempts(), r.fallbackUsed(), r.promptTokens(),
                    r.completionTokens(), r.costUsd(), r.latencyMs(), r.errorType(), r.requestSha256(), preview);
        } catch (DataAccessException e) {
            // Losing an audit row is an incident; it is logged loudly, but the caller still gets its answer.
            log.error("AUDIT WRITE FAILED for request {}: {}", r.requestId(), e.getClass().getSimpleName());
        }
    }

    public record Verification(long rows, boolean intact, List<Long> brokenAt) {
    }

    /** Recompute every row's hash and check each row points at the previous row's hash. */
    public Verification verify() {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT id, prev_hash, row_hash, gateway.audit_log_hash(a, a.prev_hash) AS expected
                FROM gateway.audit_log a ORDER BY id""");
        List<Long> broken = new ArrayList<>();
        String previous = null;
        for (Map<String, Object> row : rows) {
            long id = ((Number) row.get("id")).longValue();
            boolean linkOk = previous == null ? row.get("prev_hash") == null : previous.equals(row.get("prev_hash"));
            if (!linkOk || !row.get("row_hash").equals(row.get("expected"))) {
                broken.add(id);
            }
            previous = (String) row.get("row_hash");
        }
        return new Verification(rows.size(), broken.isEmpty(), broken);
    }
}
