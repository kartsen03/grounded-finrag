package dev.finrag.gateway.audit;

import java.math.BigDecimal;

/** One audit row. Holds metadata and a hash of the request, never the raw prompt. */
public record AuditRecord(String requestId, String clientId, String endpoint, String modelAlias, String provider,
        String upstreamModel, String outcome, int httpStatus, boolean cacheHit, int attempts, boolean fallbackUsed,
        int promptTokens, int completionTokens, BigDecimal costUsd, long latencyMs, String errorType,
        String requestSha256, String requestPreview) {

    public static AuditRecord rejected(String requestId, String clientId, String endpoint, String outcome,
            int status) {
        return new AuditRecord(requestId, clientId, endpoint, null, null, null, outcome, status, false, 0, false, 0,
                0, BigDecimal.ZERO, 0, null, null, null);
    }
}
