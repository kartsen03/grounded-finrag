package dev.finrag.gateway.api;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import dev.finrag.gateway.api.Dtos.ChatRequest;
import dev.finrag.gateway.api.Dtos.ChatResponse;
import dev.finrag.gateway.api.Dtos.EmbeddingRequest;
import dev.finrag.gateway.api.Dtos.EmbeddingResponse;
import dev.finrag.gateway.api.Dtos.RerankRequest;
import dev.finrag.gateway.api.Dtos.RerankResponse;
import dev.finrag.gateway.service.GatewayService;
import dev.finrag.gateway.web.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/v1")
public class ModelController {

    private final GatewayService service;

    public ModelController(GatewayService service) {
        this.service = service;
    }

    @PostMapping("/chat/completions")
    public ChatResponse chat(@Valid @RequestBody ChatRequest body, HttpServletRequest request) {
        return service.chat(body, RequestIdFilter.of(request));
    }

    @PostMapping("/embeddings")
    public EmbeddingResponse embeddings(@Valid @RequestBody EmbeddingRequest body, HttpServletRequest request) {
        return service.embed(body, RequestIdFilter.of(request));
    }

    @PostMapping("/rerank")
    public RerankResponse rerank(@Valid @RequestBody RerankRequest body, HttpServletRequest request) {
        return service.rerank(body, RequestIdFilter.of(request));
    }
}
