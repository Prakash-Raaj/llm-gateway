# Tables the app needs; IF NOT EXISTS makes this safe to run on every startup
SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,               -- label, e.g. "my-laptop"
    key_prefix  TEXT NOT NULL,               -- first chars of the key, to recognize it in lists
    key_hash    TEXT NOT NULL UNIQUE,        -- SHA-256 of the full key (never the key itself)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ                  -- NULL = active; set = revoked
);

ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS rpm_limit INT NOT NULL DEFAULT 60;

CREATE TABLE IF NOT EXISTS usage_logs (
    id                BIGSERIAL PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_key_id        BIGINT REFERENCES api_keys(id),  -- who called
    model             TEXT NOT NULL,                   -- name the client asked for
    provider          TEXT,                            -- NULL if the model was unknown
    provider_model    TEXT,                            -- provider's real model ID
    stream            BOOLEAN NOT NULL,
    status_code       INT NOT NULL,
    prompt_tokens     INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    latency_ms        INT NOT NULL,
    cost_usd          NUMERIC(12, 8) NOT NULL DEFAULT 0,
    error             TEXT
);

-- Fast lookups like "usage for key X this month"
CREATE INDEX IF NOT EXISTS usage_logs_key_time ON usage_logs (api_key_id, created_at);
"""


# Create tables if they don't exist yet
async def init_db(pool) -> None:
    await pool.execute(SCHEMA)

