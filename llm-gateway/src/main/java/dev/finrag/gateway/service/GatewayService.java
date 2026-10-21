package dev.finrag.gateway.service;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.springframework.stereotype.Service;

import dev.finrag.gateway.accounting.UsageAccounting;
import dev.finrag.gateway.api.Dtos.ChatRequest;
import dev.finrag.gateway.api.Dtos.ChatResponse;
import dev.finrag.gateway.api.Dtos.EmbeddingRequest;
import dev.finrag.gateway.api.Dtos.EmbeddingResponse;
import dev.finrag.gateway.api.Dtos.Message;
import dev.finrag.gateway.api.Dtos.RerankRequest;
import dev.finrag.gateway.api.Dtos.RerankResponse;
import dev.finrag.gateway.api.Dtos.Usage;
import dev.finrag.gateway.audit.AuditLog;
import dev.finrag.gateway.audit.AuditRecord;
import dev.finrag.gateway.cache.ResponseCache;
import dev.finrag.gateway.config.GatewayProperties;
import dev.finrag.gateway.config.GatewayProperties.ModelKind;
import dev.finrag.gateway.provider.ModelProvider.ChatCall;
import dev.finrag.gateway.provider.ModelProvider.ChatResult;
import dev.finrag.gateway.provider.ModelProvider.EmbedResult;
import dev.finrag.gateway.provider.ModelProvider.RerankResult;
import dev.finrag.gateway.provider.ProviderException;
import dev.finrag.gateway.resilience.ResilientCaller;
import dev.finrag.gateway.routing.ModelRouter;
import dev.finrag.gateway.routing.ModelRouter.Route;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import tools.jackson.databind.ObjectMapper;

/**
 * The request path inside the gateway, for every model kind:
 * <ol>
 * <li>cache lookup (deterministic requests only);</li>
 * <li>routes in order (primary, then fallbacks), each call wrapped in retry + circuit breaker;</li>
 * <li>token, cost and latency accounting (metrics);</li>
 * <li>one append-only audit row, whatever the outcome.</li>
 * </ol>
 */
@Service
public class GatewayService {

    private final ModelRouter router;
    private final ResilientCaller caller;
    private final ResponseCache cache;
    private final UsageAccounting accounting;
    private final AuditLog audit;
    private final ObjectMapper mapper;

    public GatewayService(ModelRouter router, ResilientCaller caller, ResponseCache cache, UsageAccounting accounting,
            AuditLog audit, ObjectMapper mapper) {
        this.router = router;
        this.caller = caller;
        this.cache = cache;
        this.accounting = accounting;
        this.audit = audit;
        this.mapper = mapper;
    }

    record Invocation<T>(T value, Route route, int attempts, boolean fallbackUsed) {
    }

    /** What one call produced, for accounting and audit. */
    private record Done(String provider, String upstream, int promptTokens, int completionTokens, int attempts,
            boolean fallback, boolean cacheHit) {
    }

    public ChatResponse chat(ChatRequest req, String rid, String client) {
        GatewayProperties.Model model = router.model(req.model(), ModelKind.CHAT);
        boolean cacheable = req.temperature() != null && req.temperature() == 0.0;
        String key = cacheable ? cache.key("chat", req) : null;
        String preview = req.messages().getLast().content();
        long t0 = System.nanoTime();
        if (key != null) {
            var hit = cache.get(key, ChatResponse.class);
            if (hit.isPresent()) {
                ChatResponse c = hit.get();
                finish("/v1/chat/completions", req.model(), model, rid, client, req, preview, t0,
                        new Done(c.provider(), null, 0, 0, 0, false, true));
                return new ChatResponse(rid, c.model(), c.provider(), c.message(), new Usage(0, 0), elapsedMs(t0), true,
                        BigDecimal.ZERO);
            }
        }
        Invocation<ChatResult> inv = invoke("/v1/chat/completions", req.model(), model, rid, client, req, preview, t0,
                ModelKind.CHAT, route -> route.provider().chat(new ChatCall(route.upstreamModel(), req.messages(),
                        req.temperature(), req.maxTokens(), req.seed(), req.responseFormat(), rid)));
        ChatResult r = inv.value();
        BigDecimal cost = finish("/v1/chat/completions", req.model(), model, rid, client, req, preview, t0,
                new Done(inv.route().provider().name(), inv.route().upstreamModel(), r.promptTokens(),
                        r.completionTokens(), inv.attempts(), inv.fallbackUsed(), false));
        ChatResponse resp = new ChatResponse(rid, req.model(), inv.route().provider().name(),
                new Message("assistant", r.content()), new Usage(r.promptTokens(), r.completionTokens()),
                elapsedMs(t0), false, cost);
        if (key != null) {
            cache.put(key, resp);
        }
        return resp;
    }

    public EmbeddingResponse embed(EmbeddingRequest req, String rid, String client) {
        GatewayProperties.Model model = router.model(req.model(), ModelKind.EMBEDDING);
        String key = req.input().size() <= cache.maxEmbeddingInputs() ? cache.key("embed", req) : null;
        String preview = req.input().getFirst();
        long t0 = System.nanoTime();
        if (key != null) {
            var hit = cache.get(key, EmbeddingResponse.class);
            if (hit.isPresent()) {
                EmbeddingResponse c = hit.get();
                finish("/v1/embeddings", req.model(), model, rid, client, req, preview, t0,
                        new Done(c.provider(), null, 0, 0, 0, false, true));
                return new EmbeddingResponse(rid, c.model(), c.provider(), c.embeddings(), new Usage(0, 0), elapsedMs(t0),
                        true, BigDecimal.ZERO);
            }
        }
        Invocation<EmbedResult> inv = invoke("/v1/embeddings", req.model(), model, rid, client, req, preview, t0,
                ModelKind.EMBEDDING, route -> route.provider().embed(route.upstreamModel(), req.input(), rid));
        EmbedResult r = inv.value();
        BigDecimal cost = finish("/v1/embeddings", req.model(), model, rid, client, req, preview, t0,
                new Done(inv.route().provider().name(), inv.route().upstreamModel(), r.inputTokens(), 0,
                        inv.attempts(), inv.fallbackUsed(), false));
        EmbeddingResponse resp = new EmbeddingResponse(rid, req.model(), inv.route().provider().name(), r.vectors(),
                new Usage(r.inputTokens(), 0), elapsedMs(t0), false, cost);
        if (key != null) {
            cache.put(key, resp);
        }
        return resp;
    }

    public RerankResponse rerank(RerankRequest req, String rid, String client) {
        GatewayProperties.Model model = router.model(req.model(), ModelKind.RERANK);
        String key = cache.key("rerank", req);
        long t0 = System.nanoTime();
        var hit = cache.get(key, RerankResponse.class);
        if (hit.isPresent()) {
            RerankResponse c = hit.get();
            finish("/v1/rerank", req.model(), model, rid, client, req, req.query(), t0,
                    new Done(c.provider(), null, 0, 0, 0, false, true));
            return new RerankResponse(rid, c.model(), c.provider(), c.scores(), new Usage(0, 0), elapsedMs(t0), true,
                    BigDecimal.ZERO);
        }
        Invocation<RerankResult> inv = invoke("/v1/rerank", req.model(), model, rid, client, req, req.query(), t0,
                ModelKind.RERANK,
                route -> route.provider().rerank(route.upstreamModel(), req.query(), req.documents(), rid));
        RerankResult r = inv.value();
        BigDecimal cost = finish("/v1/rerank", req.model(), model, rid, client, req, req.query(), t0,
                new Done(inv.route().provider().name(), inv.route().upstreamModel(), r.inputTokens(), 0,
                        inv.attempts(), inv.fallbackUsed(), false));
        RerankResponse resp = new RerankResponse(rid, req.model(), inv.route().provider().name(), r.scores(),
                new Usage(r.inputTokens(), 0), elapsedMs(t0), false, cost);
        cache.put(key, resp);
        return resp;
    }

    /**
     * Try each route in order. Retryable failures and open circuits move on to the next route;
     * a non-retryable failure (the request itself is bad) stops immediately. Failures are audited
     * here before the exception reaches the error handler.
     */
    <T> Invocation<T> invoke(String endpoint, String alias, GatewayProperties.Model model, String rid, String client,
            Object req, String preview, long t0, ModelKind kind, Function<Route, T> call) {
        List<Route> routes = router.routes(alias, kind);
        AtomicInteger attempts = new AtomicInteger();
        ProviderException last = null;
        for (int i = 0; i < routes.size(); i++) {
            Route route = routes.get(i);
            try {
                T value = caller.call(route.provider().name(), () -> call.apply(route), attempts).value();
                return new Invocation<>(value, route, attempts.get(), i > 0);
            } catch (CallNotPermittedException e) {
                last = new ProviderException(route.provider().name(), "circuit open", true, e);
            } catch (ProviderException e) {
                last = e;
                if (!e.retryable()) {
                    break;
                }
            }
        }
        long latency = elapsedMs(t0);
        accounting.record(alias, last.provider(), client, "error", false, 0, 0, BigDecimal.ZERO, latency);
        audit.record(new AuditRecord(rid, client, endpoint, alias, last.provider(), null, "error", 502, false,
                attempts.get(), routes.size() > 1, 0, 0, BigDecimal.ZERO, latency, last.getMessage(), hash(req),
                preview));
        throw last;
    }

    private BigDecimal finish(String endpoint, String alias, GatewayProperties.Model model, String rid, String client,
            Object req, String preview, long t0, Done d) {
        long latency = elapsedMs(t0);
        BigDecimal cost = d.cacheHit() ? BigDecimal.ZERO
                : UsageAccounting.cost(model, d.promptTokens(), d.completionTokens());
        accounting.record(alias, d.provider(), client, "ok", d.cacheHit(), d.promptTokens(), d.completionTokens(), cost,
                latency);
        audit.record(new AuditRecord(rid, client, endpoint, alias, d.provider(), d.upstream(), "ok", 200, d.cacheHit(),
                d.attempts(), d.fallback(), d.promptTokens(), d.completionTokens(), cost, latency, null, hash(req),
                preview));
        return cost;
    }

    private String hash(Object req) {
        return ResponseCache.sha256(mapper.writeValueAsString(req));
    }

    private static long elapsedMs(long t0) {
        return (System.nanoTime() - t0) / 1_000_000;
    }
}
