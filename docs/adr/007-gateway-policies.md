# ADR 007: Gateway policies: what is retried, cached, limited and audited

**Status:** accepted (2026-10-21)

- **Retries** only for retryable failures (timeouts, I/O, 429, 5xx), up to 3 attempts with
  exponential backoff. A 4xx is the caller's error and is neither retried nor sent to a fallback.
- **Circuit breaker** per provider (50% failure rate over 20 calls, 30 s open). Open circuits
  skip the provider without a network call, so fallback is immediate.
- **Fallback** order is per model alias. The hosted fallback for `local-chat` exists only when
  `OPENAI_API_KEY` is set, because falling back to a hosted model sends prompt data off the
  machine; that must be an explicit configuration choice.
- **Rate limit:** fixed one-minute window per client in Redis (atomic Lua). Fail-open when Redis
  is unreachable (availability over strictness for an internal service), configurable.
- **Cache** only deterministic requests: temperature-0 chat, re-ranking, embedding batches of up
  to 16 texts (query-time traffic; bulk indexing would only fill memory). Hits report zero tokens
  and zero cost.
- **Audit:** one row per request, including 401s and 429s, in an append-only PostgreSQL table.
  Triggers reject UPDATE, DELETE and TRUNCATE; an insert trigger chains each row's SHA-256 to the
  previous row under an advisory lock, so ids follow chain order under concurrency. Rows store a
  hash of the request and a redacted 160-character preview, never full prompts.
- **Redaction:** every log line passes through a Logback converter that masks keys, tokens,
  emails, phone numbers, SSNs and Luhn-valid card numbers.
