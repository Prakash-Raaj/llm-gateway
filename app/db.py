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
"""


# Create tables if they don't exist yet
async def init_db(pool) -> None:
    await pool.execute(SCHEMA)
