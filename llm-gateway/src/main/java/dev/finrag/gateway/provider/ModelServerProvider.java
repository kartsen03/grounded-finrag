package dev.finrag.gateway.provider;

import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** The local Python model server (model-server/app.py): BGE embeddings and the cross-encoder re-ranker. */
public class ModelServerProvider implements ModelProvider {

    private final String name;
    private final RestClient client;

    public ModelServerProvider(String name, RestClient client) {
        this.name = name;
        this.client = client;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public EmbedResult embed(String upstreamModel, List<String> input, String requestId) {
        try {
            EmbedReply reply = client.post().uri("/embed").contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", requestId)
                    .body(Map.of("model", upstreamModel, "texts", input, "normalize", true)).retrieve()
                    .body(EmbedReply.class);
            return new EmbedResult(reply.embeddings(), reply.inputTokens());
        } catch (RuntimeException e) {
            throw ProviderException.from(name, e);
        }
    }

    @Override
    public RerankResult rerank(String upstreamModel, String query, List<String> documents, String requestId) {
        try {
            RerankReply reply = client.post().uri("/rerank").contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", requestId)
                    .body(Map.of("model", upstreamModel, "query", query, "documents", documents)).retrieve()
                    .body(RerankReply.class);
            return new RerankResult(reply.scores(), reply.inputTokens());
        } catch (RuntimeException e) {
            throw ProviderException.from(name, e);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record EmbedReply(List<float[]> embeddings, @JsonProperty("input_tokens") int inputTokens) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record RerankReply(List<Double> scores, @JsonProperty("input_tokens") int inputTokens) {
    }
}
