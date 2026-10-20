package dev.finrag.gateway.provider;

import java.util.List;
import java.util.Map;

import dev.finrag.gateway.api.Dtos.Message;

/**
 * One upstream model provider (Ollama, the local model server, a hosted API). Adapters
 * translate the gateway's request shapes into the provider's API and back; everything
 * else (auth, routing, resilience, accounting) lives in the gateway around them.
 */
public interface ModelProvider {

    String name();

    default ChatResult chat(ChatCall call) {
        throw new UnsupportedOperationException(name() + " does not serve chat models");
    }

    default EmbedResult embed(String upstreamModel, List<String> input, String requestId) {
        throw new UnsupportedOperationException(name() + " does not serve embedding models");
    }

    default RerankResult rerank(String upstreamModel, String query, List<String> documents, String requestId) {
        throw new UnsupportedOperationException(name() + " does not serve re-ranking models");
    }

    record ChatCall(String upstreamModel, List<Message> messages, Double temperature, Integer maxTokens, Integer seed,
            Map<String, Object> jsonSchema, String requestId) {
    }

    record ChatResult(String content, int promptTokens, int completionTokens) {
    }

    record EmbedResult(List<float[]> vectors, int inputTokens) {
    }

    record RerankResult(List<Double> scores, int inputTokens) {
    }
}
