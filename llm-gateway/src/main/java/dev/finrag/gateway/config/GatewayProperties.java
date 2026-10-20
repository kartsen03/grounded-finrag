package dev.finrag.gateway.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Gateway configuration: which clients may call it, which upstream providers exist, and
 * which public model aliases route to which provider and upstream model.
 */
@ConfigurationProperties("gateway")
public record GatewayProperties(List<Client> clients, Map<String, Provider> providers, Map<String, Model> models) {

    /** A calling application. Only the SHA-256 of its API key is stored. */
    public record Client(String id, String keySha256) {
    }

    /**
     * An upstream model provider. A provider with a blank {@code apiKey} that needs one
     * (hosted providers) is disabled. {@code contextLength} sets Ollama's num_ctx, whose
     * default is too small for RAG prompts.
     */
    public record Provider(ProviderType type, String baseUrl, Duration connectTimeout, Duration readTimeout,
            String apiKey, Integer contextLength) {
    }

    /** A public model alias, e.g. "local-chat" -> ollama / qwen2.5:7b-instruct-q4_K_M. */
    public record Model(ModelKind kind, String provider, String upstream) {
    }

    public enum ProviderType {
        OLLAMA, MODEL_SERVER, OPENAI
    }

    public enum ModelKind {
        CHAT, EMBEDDING, RERANK
    }
}
