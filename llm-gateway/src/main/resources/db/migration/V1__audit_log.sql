-- Functions pin search_path, because triggers run with the caller's search_path (public).
-- Append-only, hash-chained audit log of every gateway request (gateway schema, owned by Flyway).
-- Rows hold metadata, token counts, cost and a hash of the request body, never raw prompts;
-- the optional preview is redacted by the application before insert.

CREATE TABLE audit_log (
    id                bigint      PRIMARY KEY,
    ts                timestamptz NOT NULL DEFAULT clock_timestamp(),
    request_id        text        NOT NULL,
    client_id         text,
    endpoint          text        NOT NULL,
    model_alias       text,
    provider          text,
    upstream_model    text,
    outcome           text        NOT NULL,   -- ok | error | rate_limited | unauthorized
    http_status       int         NOT NULL,
    cache_hit         boolean     NOT NULL DEFAULT false,
    attempts          int         NOT NULL DEFAULT 0,
    fallback_used     boolean     NOT NULL DEFAULT false,
    prompt_tokens     int         NOT NULL DEFAULT 0,
    completion_tokens int         NOT NULL DEFAULT 0,
    cost_usd          numeric(14, 8) NOT NULL DEFAULT 0,
    latency_ms        bigint      NOT NULL DEFAULT 0,
    error_type        text,
    request_sha256    text,
    request_preview   text,
    prev_hash         text,
    row_hash          text        NOT NULL
);

CREATE SEQUENCE audit_log_id_seq;
CREATE INDEX audit_log_request_id ON audit_log (request_id);
CREATE INDEX audit_log_ts ON audit_log (ts);

-- Hash of one row's content chained to the previous row's hash. Used on insert and when verifying.
CREATE FUNCTION audit_log_hash(r audit_log, prev text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = gateway, pg_catalog AS $$
    SELECT encode(sha256(convert_to(concat_ws('|',
        coalesce(prev, ''), r.id, to_char(r.ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        r.request_id, coalesce(r.client_id, ''), r.endpoint, coalesce(r.model_alias, ''),
        coalesce(r.provider, ''), coalesce(r.upstream_model, ''), r.outcome, r.http_status, r.cache_hit,
        r.attempts, r.fallback_used, r.prompt_tokens, r.completion_tokens, r.cost_usd, r.latency_ms,
        coalesce(r.error_type, ''), coalesce(r.request_sha256, ''), coalesce(r.request_preview, '')), 'UTF8')), 'hex')
$$;

-- Serialize inserts with a transaction-scoped advisory lock, then take the next id and chain the
-- row to the latest one, so ids follow chain order even under concurrent requests.
CREATE FUNCTION audit_log_chain() RETURNS trigger
LANGUAGE plpgsql SET search_path = gateway, pg_catalog AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(727274);
    NEW.id := nextval('audit_log_id_seq');
    SELECT row_hash INTO NEW.prev_hash FROM audit_log ORDER BY id DESC LIMIT 1;
    NEW.row_hash := audit_log_hash(NEW, NEW.prev_hash);
    RETURN NEW;
END $$;

CREATE TRIGGER audit_log_chain BEFORE INSERT ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_chain();

CREATE FUNCTION audit_log_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = gateway, pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END $$;

CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only();
