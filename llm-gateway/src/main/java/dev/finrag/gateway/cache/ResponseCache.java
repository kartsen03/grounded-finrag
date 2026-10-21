package dev.finrag.gateway.cache;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * Redis cache of model responses, keyed by the SHA-256 of the canonical request JSON (model
 * alias included). Only deterministic requests are cached; the decision is the caller's.
 * Best effort: a Redis failure is logged and treated as a miss, never as an error.
 */
@Component
public class ResponseCache {

    private static final Logger log = LoggerFactory.getLogger(ResponseCache.class);
    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    private final GatewayProperties.Cache settings;

    public ResponseCache(StringRedisTemplate redis, ObjectMapper mapper, GatewayProperties properties) {
        this.redis = redis;
        this.mapper = mapper;
        this.settings = properties.cache();
    }

    public boolean enabled() {
        return settings.enabled();
    }

    public String key(String kind, Object request) {
        return "gw:cache:" + kind + ":" + sha256(mapper.writeValueAsString(request));
    }

    public <T> Optional<T> get(String key, Class<T> type) {
        if (!settings.enabled()) {
            return Optional.empty();
        }
        try {
            String json = redis.opsForValue().get(key);
            return json == null ? Optional.empty() : Optional.of(mapper.readValue(json, type));
        } catch (DataAccessException | JacksonException e) {
            log.warn("cache read failed: {}", e.getClass().getSimpleName());
            return Optional.empty();
        }
    }

    public void put(String key, Object value) {
        if (!settings.enabled()) {
            return;
        }
        try {
            redis.opsForValue().set(key, mapper.writeValueAsString(value), settings.ttl());
        } catch (DataAccessException | JacksonException e) {
            log.warn("cache write failed: {}", e.getClass().getSimpleName());
        }
    }

    public int maxEmbeddingInputs() {
        return settings.maxEmbeddingInputs();
    }

    public static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
