package dev.finrag.gateway;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Real Redis and PostgreSQL (the same pinned images as docker-compose) shared by integration
 * tests, started once per JVM. Rate limiting, caching and the audit triggers are tested against
 * the real thing rather than mocks.
 */
public abstract class IntegrationTestBase {

    static final GenericContainer<?> REDIS = new GenericContainer<>(DockerImageName.parse("redis:7.2.16-alpine"))
            .withCommand("redis-server", "--requirepass", "test-redis").withExposedPorts(6379);

    static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer(
            DockerImageName.parse("pgvector/pgvector:0.8.7-pg17-bookworm").asCompatibleSubstituteFor("postgres"));

    static {
        REDIS.start();
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void containers(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("spring.data.redis.password", () -> "test-redis");
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
