package dev.finrag.gateway.ratelimit;

import java.io.IOException;

import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import dev.finrag.gateway.audit.AuditLog;
import dev.finrag.gateway.audit.AuditRecord;
import dev.finrag.gateway.web.ApiKeyFilter;
import dev.finrag.gateway.web.RequestIdFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/** Applies the per-client limit after authentication; rejected requests get 429 and are audited. */
@Component
@Order(2)
public class RateLimitFilter extends OncePerRequestFilter {

    private final RateLimiter limiter;
    private final AuditLog audit;

    public RateLimitFilter(RateLimiter limiter, AuditLog audit) {
        this.limiter = limiter;
        this.audit = audit;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/v1/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String client = (String) request.getAttribute(ApiKeyFilter.CLIENT_ATTRIBUTE);
        RateLimiter.Decision d = limiter.check(client);
        response.setHeader("X-RateLimit-Limit", String.valueOf(d.limit()));
        response.setHeader("X-RateLimit-Remaining", String.valueOf(d.remaining()));
        if (!d.allowed()) {
            String rid = RequestIdFilter.of(request);
            response.setStatus(429);
            response.setHeader("Retry-After", String.valueOf(d.retryAfterSeconds()));
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"request_id\":\"" + rid + "\",\"type\":\"rate_limited\","
                    + "\"message\":\"rate limit exceeded\"}");
            audit.record(AuditRecord.rejected(rid, client, request.getRequestURI(), "rate_limited", 429));
            return;
        }
        chain.doFilter(request, response);
    }
}
