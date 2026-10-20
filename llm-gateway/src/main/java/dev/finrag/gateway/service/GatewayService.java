package dev.finrag.gateway.service;

import org.springframework.stereotype.Service;

import dev.finrag.gateway.api.Dtos.ChatRequest;
import dev.finrag.gateway.api.Dtos.ChatResponse;
import dev.finrag.gateway.api.Dtos.EmbeddingRequest;
import dev.finrag.gateway.api.Dtos.EmbeddingResponse;
import dev.finrag.gateway.api.Dtos.Message;
import dev.finrag.gateway.api.Dtos.RerankRequest;
import dev.finrag.gateway.api.Dtos.RerankResponse;
import dev.finrag.gateway.api.Dtos.Usage;
import dev.finrag.gateway.config.GatewayProperties.ModelKind;
import dev.finrag.gateway.provider.ModelProvider.ChatCall;
import dev.finrag.gateway.provider.ModelProvider.ChatResult;
import dev.finrag.gateway.provider.ModelProvider.EmbedResult;
import dev.finrag.gateway.provider.ModelProvider.RerankResult;
import dev.finrag.gateway.routing.ModelRouter;
import dev.finrag.gateway.routing.ModelRouter.Route;

/** Routes each call to its provider and measures it. */
@Service
public class GatewayService {

    private final ModelRouter router;

    public GatewayService(ModelRouter router) {
        this.router = router;
    }

    public ChatResponse chat(ChatRequest req, String requestId) {
        Route route = router.route(req.model(), ModelKind.CHAT);
        long t0 = System.nanoTime();
        ChatResult r = route.provider().chat(new ChatCall(route.upstreamModel(), req.messages(), req.temperature(),
                req.maxTokens(), req.seed(), req.responseFormat(), requestId));
        return new ChatResponse(requestId, req.model(), route.provider().name(), new Message("assistant", r.content()),
                new Usage(r.promptTokens(), r.completionTokens()), elapsedMs(t0));
    }

    public EmbeddingResponse embed(EmbeddingRequest req, String requestId) {
        Route route = router.route(req.model(), ModelKind.EMBEDDING);
        long t0 = System.nanoTime();
        EmbedResult r = route.provider().embed(route.upstreamModel(), req.input(), requestId);
        return new EmbeddingResponse(requestId, req.model(), route.provider().name(), r.vectors(),
                new Usage(r.inputTokens(), 0), elapsedMs(t0));
    }

    public RerankResponse rerank(RerankRequest req, String requestId) {
        Route route = router.route(req.model(), ModelKind.RERANK);
        long t0 = System.nanoTime();
        RerankResult r = route.provider().rerank(route.upstreamModel(), req.query(), req.documents(), requestId);
        return new RerankResponse(requestId, req.model(), route.provider().name(), r.scores(),
                new Usage(r.inputTokens(), 0), elapsedMs(t0));
    }

    private static long elapsedMs(long t0) {
        return (System.nanoTime() - t0) / 1_000_000;
    }
}
