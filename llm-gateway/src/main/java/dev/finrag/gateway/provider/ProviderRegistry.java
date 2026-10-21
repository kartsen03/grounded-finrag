package dev.finrag.gateway.provider;

import java.net.http.HttpClient;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import dev.finrag.gateway.config.GatewayProperties;

/** Builds one adapter per configured provider, each with its own connect and read timeouts. */
@Component
public class ProviderRegistry {

    private static final Logger log = LoggerFactory.getLogger(ProviderRegistry.class);
    private final Map<String, ModelProvider> providers = new LinkedHashMap<>();

    public ProviderRegistry(GatewayProperties properties) {
        properties.providers().forEach((name, p) -> create(name, p, RestClient.builder()).ifPresentOrElse(
                provider -> providers.put(name, provider),
                () -> log.info("provider {} disabled (no API key configured)", name)));
    }

    /** Package-private for tests, which pass a builder bound to a mock server. */
    static Optional<ModelProvider> create(String name, GatewayProperties.Provider p, RestClient.Builder builder) {
        HttpClient http = httpClient(p);
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(p.readTimeout());
        builder = builder.baseUrl(p.baseUrl()).requestFactory(factory);
        return switch (p.type()) {
            case OLLAMA -> Optional.of(new OllamaProvider(name, builder.build(), p.contextLength()));
            case MODEL_SERVER -> Optional.of(new ModelServerProvider(name, builder.build()));
            case OPENAI -> p.apiKey() == null || p.apiKey().isBlank() ? Optional.empty()
                    : Optional.of(new OpenAiProvider(name,
                            builder.defaultHeader("Authorization", "Bearer " + p.apiKey()).build()));
        };
    }

    /**
     * HTTP/1.1 on purpose: the JDK client defaults to HTTP/2 and, over plain http, sends an
     * "Upgrade: h2c" request with a chunked body that uvicorn (model server) answers as if the
     * body were empty (HTTP 422).
     */
    static HttpClient httpClient(GatewayProperties.Provider p) {
        return HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(p.connectTimeout()).build();
    }

    public Optional<ModelProvider> get(String name) {
        return Optional.ofNullable(providers.get(name));
    }
}
