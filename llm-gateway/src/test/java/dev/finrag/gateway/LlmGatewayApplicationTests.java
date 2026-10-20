package dev.finrag.gateway;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import dev.finrag.gateway.api.Dtos.RerankResponse;
import dev.finrag.gateway.api.Dtos.Usage;
import dev.finrag.gateway.service.GatewayService;

/** End-to-end through the servlet filters: authentication, request IDs, validation, routing errors. */
@SpringBootTest
@AutoConfigureMockMvc
class LlmGatewayApplicationTests {

    private static final String KEY = "dev-rag-service-key";
    private static final String RERANK = "{\"model\":\"bge-reranker-base\",\"query\":\"q\",\"documents\":[\"a\",\"b\"]}";

    @Autowired
    MockMvc mvc;

    @MockitoBean
    GatewayService service;

    @Test
    void rejectsMissingAndWrongApiKeys() throws Exception {
        mvc.perform(post("/v1/rerank").contentType(MediaType.APPLICATION_JSON).content(RERANK))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.type").value("unauthorized"));
        mvc.perform(post("/v1/rerank").header("X-API-Key", "wrong").contentType(MediaType.APPLICATION_JSON)
                .content(RERANK)).andExpect(status().isUnauthorized());
    }

    @Test
    void acceptsValidKeyAndEchoesRequestId() throws Exception {
        when(service.rerank(any(), eq("req-123"))).thenReturn(
                new RerankResponse("req-123", "bge-reranker-base", "local-models", List.of(0.9, 0.1), new Usage(10, 0), 5));
        mvc.perform(post("/v1/rerank").header("Authorization", "Bearer " + KEY).header("X-Request-Id", "req-123")
                .contentType(MediaType.APPLICATION_JSON).content(RERANK))
                .andExpect(status().isOk()).andExpect(header().string("X-Request-Id", "req-123"))
                .andExpect(jsonPath("$.request_id").value("req-123")).andExpect(jsonPath("$.scores[0]").value(0.9))
                .andExpect(jsonPath("$.usage.total_tokens").value(10));
    }

    @Test
    void replacesUnsafeRequestIds() throws Exception {
        mvc.perform(get("/actuator/health").header("X-Request-Id", "bad id\r\nX-Injected: 1"))
                .andExpect(header().string("X-Request-Id", org.hamcrest.Matchers.matchesPattern("[0-9a-f-]{36}")));
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/actuator/health")).andExpect(status().isOk());
    }

    @Test
    void validatesBodies() throws Exception {
        mvc.perform(post("/v1/rerank").header("X-API-Key", KEY).contentType(MediaType.APPLICATION_JSON)
                .content("{\"model\":\"bge-reranker-base\",\"query\":\"q\",\"documents\":[]}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.type").value("invalid_request"));
    }
}
