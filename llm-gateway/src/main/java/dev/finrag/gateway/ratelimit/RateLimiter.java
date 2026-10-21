package dev.finrag.gateway.ratelimit;

import java.time.Clock;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Component;

import dev.finrag.gateway.config.GatewayProperties;

/**
 * Fixed-window rate limit per client: one Redis counter per client per minute.
 * INCR and EXPIRE run in one Lua script, so concurrent requests across gateway instances
 * share the count atomically and a counter can never be left without a TTL.
 */
@Component
public class RateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RateLimiter.class);
    private static final RedisScript<Long> INCR_WITH_TTL = RedisScript.of(
            "local c = redis.call('INCR', KEYS[1]) if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end return c",
            Long.class);

    private final StringRedisTemplate redis;
    private final GatewayProperties properties;
    private final Clock clock;

    @Autowired
    public RateLimiter(StringRedisTemplate redis, GatewayProperties properties) {
        this(redis, properties, Clock.systemUTC());
    }

    RateLimiter(StringRedisTemplate redis, GatewayProperties properties, Clock clock) {
        this.redis = redis;
        this.properties = properties;
        this.clock = clock;
    }

    public record Decision(boolean allowed, int limit, long remaining, long retryAfterSeconds, boolean degraded) {
    }

    public Decision check(String clientId) {
        int limit = limitFor(clientId);
        long epochSecond = clock.instant().getEpochSecond();
        long window = epochSecond / 60;
        long retryAfter = 60 - (epochSecond % 60);
        try {
            Long count = redis.execute(INCR_WITH_TTL, List.of("gw:rl:" + clientId + ":" + window), "61");
            long used = count == null ? 0 : count;
            return new Decision(used <= limit, limit, Math.max(0, limit - used), retryAfter, false);
        } catch (DataAccessException e) {
            // Redis down: availability vs strictness is a policy choice; it is configurable.
            boolean allow = properties.rateLimit().failOpen();
            log.warn("rate limiter unavailable ({}); {} request", e.getClass().getSimpleName(),
                    allow ? "allowing" : "rejecting");
            return new Decision(allow, limit, 0, retryAfter, true);
        }
    }

    int limitFor(String clientId) {
        return properties.clients().stream().filter(c -> clientId != null && clientId.equals(c.id()) && c.requestsPerMinute() != null)
                .map(GatewayProperties.Client::requestsPerMinute).findFirst()
                .orElse(properties.rateLimit().requestsPerMinute());
    }
}
