package dev.finrag.gateway.provider;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.http.HttpClient;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import dev.finrag.gateway.config.GatewayProperties.Provider;
import dev.finrag.gateway.config.GatewayProperties.ProviderType;

class ProviderRegistryTests {

    private static Provider provider(ProviderType type, String key) {
        return new Provider(type, "http://localhost:1", Duration.ofSeconds(1), Duration.ofSeconds(2), key, null);
    }

    @Test
    void upstreamClientsUseHttp11() {
        // Regression: HTTP/2 upgrade requests lost their body at the uvicorn model server.
        assertThat(ProviderRegistry.httpClient(provider(ProviderType.MODEL_SERVER, null)).version())
                .isEqualTo(HttpClient.Version.HTTP_1_1);
    }

    @Test
    void hostedProviderWithoutKeyIsDisabled() {
        assertThat(ProviderRegistry.create("openai", provider(ProviderType.OPENAI, ""), RestClient.builder())).isEmpty();
        assertThat(ProviderRegistry.create("openai", provider(ProviderType.OPENAI, "sk-test"), RestClient.builder()))
                .isPresent();
        assertThat(ProviderRegistry.create("ollama", provider(ProviderType.OLLAMA, null), RestClient.builder()))
                .get().isInstanceOf(OllamaProvider.class);
    }
}
