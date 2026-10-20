package dev.finrag.gateway.api;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

/** Request and response bodies of the gateway's public API. JSON uses snake_case. */
public final class Dtos {

    private Dtos() {
    }

    public record Message(@NotBlank String role, @NotBlank String content) {
    }

    /**
     * Chat completion. {@code responseFormat}, when present, is a JSON Schema the answer
     * must follow (passed to Ollama's structured-output "format" field).
     */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record ChatRequest(@NotBlank String model, @NotEmpty @Valid List<Message> messages, Double temperature,
            @JsonProperty("max_tokens") Integer maxTokens, Integer seed,
            @JsonProperty("response_format") Map<String, Object> responseFormat) {
    }

    public record Usage(@JsonProperty("prompt_tokens") int promptTokens,
            @JsonProperty("completion_tokens") int completionTokens) {

        @JsonProperty("total_tokens")
        public int totalTokens() {
            return promptTokens + completionTokens;
        }
    }

    public record ChatResponse(@JsonProperty("request_id") String requestId, String model, String provider,
            Message message, Usage usage, @JsonProperty("latency_ms") long latencyMs) {
    }

    public record EmbeddingRequest(@NotBlank String model, @NotEmpty @Size(max = 512) List<@NotBlank String> input) {
    }

    public record EmbeddingResponse(@JsonProperty("request_id") String requestId, String model, String provider,
            List<float[]> embeddings, Usage usage, @JsonProperty("latency_ms") long latencyMs) {
    }

    public record RerankRequest(@NotBlank String model, @NotBlank String query,
            @NotEmpty @Size(max = 512) List<@NotBlank String> documents) {
    }

    public record RerankResponse(@JsonProperty("request_id") String requestId, String model, String provider,
            List<Double> scores, Usage usage, @JsonProperty("latency_ms") long latencyMs) {
    }

    public record ErrorBody(@JsonProperty("request_id") String requestId, String type, String message) {
    }
}
