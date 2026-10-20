package dev.finrag.gateway.provider;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import dev.finrag.gateway.api.Dtos.Message;
import dev.finrag.gateway.provider.ModelProvider.ChatCall;

/** Adapters translate requests to each provider's API, forward the request ID and map failures. */
class ProviderAdapterTests {

    @Test
    void ollamaChatSendsOptionsSchemaAndRequestId() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://ollama");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("http://ollama/api/chat")).andExpect(header("X-Request-Id", "r1"))
                .andExpect(jsonPath("$.stream").value(false)).andExpect(jsonPath("$.options.num_ctx").value(8192))
                .andExpect(jsonPath("$.options.temperature").value(0.0)).andExpect(jsonPath("$.format.type").value("object"))
                .andRespond(withSuccess("{\"message\":{\"role\":\"assistant\",\"content\":\"42\"},"
                        + "\"prompt_eval_count\":100,\"eval_count\":7,\"done\":true}", MediaType.APPLICATION_JSON));
        OllamaProvider ollama = new OllamaProvider("ollama", builder.build(), 8192);

        ModelProvider.ChatResult result = ollama.chat(new ChatCall("qwen", List.of(new Message("user", "hi")), 0.0,
                null, null, Map.of("type", "object"), "r1"));

        assertThat(result.content()).isEqualTo("42");
        assertThat(result.promptTokens()).isEqualTo(100);
        assertThat(result.completionTokens()).isEqualTo(7);
        server.verify();
    }

    @Test
    void modelServerRerankParsesScores() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://models");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("http://models/rerank")).andExpect(jsonPath("$.documents.length()").value(2))
                .andRespond(withSuccess("{\"scores\":[0.7,0.2],\"input_tokens\":31}", MediaType.APPLICATION_JSON));

        ModelProvider.RerankResult r = new ModelServerProvider("local", builder.build())
                .rerank("bge-reranker-base", "q", List.of("a", "b"), "r2");

        assertThat(r.scores()).containsExactly(0.7, 0.2);
        assertThat(r.inputTokens()).isEqualTo(31);
    }

    @Test
    void serverErrorsAreRetryableClientErrorsAreNot() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://models");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("http://models/embed")).andRespond(withServerError());
        server.expect(requestTo("http://models/embed")).andRespond(withStatus(HttpStatus.BAD_REQUEST));
        ModelServerProvider provider = new ModelServerProvider("local", builder.build());

        assertThatThrownBy(() -> provider.embed("m", List.of("x"), "r3")).isInstanceOfSatisfying(ProviderException.class,
                e -> assertThat(e.retryable()).isTrue());
        assertThatThrownBy(() -> provider.embed("m", List.of("x"), "r4")).isInstanceOfSatisfying(ProviderException.class,
                e -> assertThat(e.retryable()).isFalse());
    }
}
