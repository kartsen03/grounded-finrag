package dev.finrag.gateway.provider;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import dev.finrag.gateway.api.Dtos.Message;

/**
 * Optional hosted provider speaking the OpenAI-compatible API. Enabled only when an API key
 * is configured (environment variable), so the default setup never sends data off the machine.
 */
public class OpenAiProvider implements ModelProvider {

    private final String name;
    private final RestClient client;

    public OpenAiProvider(String name, RestClient client) {
        this.name = name;
        this.client = client;
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public ChatResult chat(ChatCall call) {
        Map<String, Object> body = new HashMap<>();
        body.put("model", call.upstreamModel());
        body.put("messages", call.messages());
        if (call.temperature() != null) {
            body.put("temperature", call.temperature());
        }
        if (call.maxTokens() != null) {
            body.put("max_tokens", call.maxTokens());
        }
        if (call.seed() != null) {
            body.put("seed", call.seed());
        }
        if (call.jsonSchema() != null) {
            body.put("response_format", Map.of("type", "json_schema",
                    "json_schema", Map.of("name", "answer", "schema", call.jsonSchema())));
        }
        try {
            ChatReply reply = client.post().uri("/v1/chat/completions").contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", call.requestId()).body(body).retrieve().body(ChatReply.class);
            Usage u = reply.usage() == null ? new Usage(0, 0) : reply.usage();
            return new ChatResult(reply.choices().getFirst().message().content(), u.promptTokens(), u.completionTokens());
        } catch (RuntimeException e) {
            throw ProviderException.from(name, e);
        }
    }

    @Override
    public EmbedResult embed(String upstreamModel, List<String> input, String requestId) {
        try {
            EmbedReply reply = client.post().uri("/v1/embeddings").contentType(MediaType.APPLICATION_JSON)
                    .header("X-Request-Id", requestId).body(Map.of("model", upstreamModel, "input", input))
                    .retrieve().body(EmbedReply.class);
            List<float[]> vectors = reply.data().stream().map(EmbedItem::embedding).toList();
            return new EmbedResult(vectors, reply.usage() == null ? 0 : reply.usage().promptTokens());
        } catch (RuntimeException e) {
            throw ProviderException.from(name, e);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Usage(@JsonProperty("prompt_tokens") int promptTokens, @JsonProperty("completion_tokens") int completionTokens) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Choice(Message message) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record ChatReply(List<Choice> choices, Usage usage) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record EmbedItem(float[] embedding) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record EmbedReply(List<EmbedItem> data, Usage usage) {
    }
}
