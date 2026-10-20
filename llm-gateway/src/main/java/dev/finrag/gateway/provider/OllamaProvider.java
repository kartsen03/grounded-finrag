package dev.finrag.gateway.provider;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import dev.finrag.gateway.api.Dtos.Message;

/** Ollama's native API: POST /api/chat (non-streaming) and POST /api/embed. */
public class OllamaProvider implements ModelProvider {

    private final String name;
    private final RestClient client;
    private final Integer contextLength;

    public OllamaProvider(String name, RestClient client, Integer contextLength) {
        this.name = name;
        this.client = client;
        this.contextLength = contextLength;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public ChatResult chat(ChatCall call) {
        Map<String, Object> options = new HashMap<>();
        if (call.temperature() != null) {
            options.put("temperature", call.temperature());
        }
        if (call.maxTokens() != null) {
            options.put("num_predict", call.maxTokens());
        }
        if (call.seed() != null) {
            options.put("seed", call.seed());
        }
        if (contextLength != null) {
            options.put("num_ctx", contextLength);
        }
        Map<String, Object> body = new HashMap<>();
        body.put("model", call.upstreamModel());
        body.put("messages", call.messages());
        body.put("stream", false);
        body.put("options", options);
        if (call.jsonSchema() != null) {
            body.put("format", call.jsonSchema());
        }
        try {
            ChatReply reply = client.post().uri("/api/chat").contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", call.requestId()).body(body).retrieve().body(ChatReply.class);
            return new ChatResult(reply.message().content(), nz(reply.promptEvalCount()), nz(reply.evalCount()));
        } catch (RuntimeException e) {
            throw ProviderException.from(name, e);
        }
    }

    @Override
    public EmbedResult embed(String upstreamModel, List<String> input, String requestId) {
        try {
            EmbedReply reply = client.post().uri("/api/embed").contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", requestId).body(Map.of("model", upstreamModel, "input", input)).retrieve()
                    .body(EmbedReply.class);
            return new EmbedResult(reply.embeddings(), nz(reply.promptEvalCount()));
        } catch (RuntimeException e) {
            throw ProviderException.from(name, e);
        }
    }

    private static int nz(Integer v) {
        return v == null ? 0 : v;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record ChatReply(Message message, @JsonProperty("prompt_eval_count") Integer promptEvalCount,
            @JsonProperty("eval_count") Integer evalCount) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record EmbedReply(List<float[]> embeddings, @JsonProperty("prompt_eval_count") Integer promptEvalCount) {
    }
}
