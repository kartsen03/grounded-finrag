package dev.finrag.gateway.config;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Gateway configuration: which clients may call it and how often, which upstream providers
 * exist, how calls to them are protected, and which public model aliases route where.
 */
@ConfigurationProperties("gateway")
public record GatewayProperties(List<Client> clients, Map<String, Provider> providers, Map<String, Model> models,
        RateLimit rateLimit, Cache cache, Resilience resilience) {

    public GatewayProperties {
        clients = clients == null ? List.of() : clients;
        providers = providers == null ? Map.of() : providers;
        models = models == null ? Map.of() : models;
        rateLimit = rateLimit == null ? new RateLimit(600, true) : rateLimit;
        cache = cache == null ? new Cache(true, Duration.ofHours(24), 16) : cache;
        resilience = resilience == null ? new Resilience(3, Duration.ofMillis(200), 50, 20, Duration.ofSeconds(30))
                : resilience;
    }

    /**
     * A calling application. Only the SHA-256 of its API key is stored. {@code requestsPerMinute}
     * overrides the default rate limit for this client.
     */
    public record Client(String id, String keySha256, Integer requestsPerMinute) {
    }

    /**
     * An upstream model provider. A provider with a blank {@code apiKey} that needs one
     * (hosted providers) is disabled. {@code contextLength} sets Ollama's num_ctx, whose
     * default is too small for RAG prompts.
     */
    public record Provider(ProviderType type, String baseUrl, Duration connectTimeout, Duration readTimeout,
            String apiKey, Integer contextLength) {
    }

    /**
     * A public model alias, e.g. "local-chat" -> ollama / qwen2.5:7b-instruct-q4_K_M, with optional
     * fallback targets tried in order when the primary is failing, and prices per 1,000 tokens
     * (USD) used for cost accounting (0 for local models).
     */
    public record Model(ModelKind kind, String provider, String upstream, List<Target> fallbacks,
            BigDecimal costPer1kPromptUsd, BigDecimal costPer1kCompletionUsd) {

        public Model {
            fallbacks = fallbacks == null ? List.of() : fallbacks;
            costPer1kPromptUsd = costPer1kPromptUsd == null ? BigDecimal.ZERO : costPer1kPromptUsd;
            costPer1kCompletionUsd = costPer1kCompletionUsd == null ? BigDecimal.ZERO : costPer1kCompletionUsd;
        }
    }

    public record Target(String provider, String upstream) {
    }

    /** Fixed one-minute window per client. {@code failOpen}: allow traffic if Redis is unreachable. */
    public record RateLimit(int requestsPerMinute, boolean failOpen) {
    }

    /**
     * Response cache for deterministic calls (temperature 0 chat, embeddings, re-ranking). Embedding
     * requests with more than {@code maxEmbeddingInputs} texts are not cached (bulk indexing).
     */
    public record Cache(boolean enabled, Duration ttl, int maxEmbeddingInputs) {
    }

    /** Retries (retryable failures only) and a circuit breaker per provider. */
    public record Resilience(int retryAttempts, Duration retryWait, float breakerFailureRatePercent,
            int breakerWindowCalls, Duration breakerOpenFor) {
    }

    public enum ProviderType {
        OLLAMA, MODEL_SERVER, OPENAI
    }

    public enum ModelKind {
        CHAT, EMBEDDING, RERANK
    }
}
