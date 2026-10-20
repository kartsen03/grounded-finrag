package dev.finrag.gateway.web;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;

import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import dev.finrag.gateway.config.GatewayProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * API-key authentication for /v1/**. Keys arrive as {@code X-API-Key} or
 * {@code Authorization: Bearer}. The gateway stores only SHA-256 hashes and compares them in
 * constant time; the matched client ID is attached to the request for rate limiting and audit.
 */
@Component
@Order(1)
public class ApiKeyFilter extends OncePerRequestFilter {

    public static final String CLIENT_ATTRIBUTE = "clientId";
    private final List<GatewayProperties.Client> clients;

    public ApiKeyFilter(GatewayProperties properties) {
        this.clients = properties.clients() == null ? List.of() : properties.clients();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/v1/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        Optional<String> client = presentedKey(request).flatMap(this::lookup);
        if (client.isEmpty()) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"request_id\":\"" + RequestIdFilter.of(request)
                    + "\",\"type\":\"unauthorized\",\"message\":\"missing or invalid API key\"}");
            return;
        }
        request.setAttribute(CLIENT_ATTRIBUTE, client.get());
        chain.doFilter(request, response);
    }

    private static Optional<String> presentedKey(HttpServletRequest request) {
        String key = request.getHeader("X-API-Key");
        if (key == null) {
            String auth = request.getHeader("Authorization");
            if (auth != null && auth.startsWith("Bearer ")) {
                key = auth.substring(7);
            }
        }
        return Optional.ofNullable(key).map(String::strip).filter(k -> !k.isEmpty());
    }

    private Optional<String> lookup(String key) {
        byte[] presented = sha256(key);
        String match = null;
        for (GatewayProperties.Client c : clients) {
            byte[] stored = HexFormat.of().parseHex(c.keySha256());
            // Check every client so timing does not reveal which entry matched.
            if (MessageDigest.isEqual(presented, stored)) {
                match = c.id();
            }
        }
        return Optional.ofNullable(match);
    }

    static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
