import os
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI


# Runs on startup (before yield) and shutdown (after yield).
@asynccontextmanager
async def lifespan(app:FastAPI):
    # Open a reusable pool of Postgres connections and a Redis client
    app.state.db = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield
    # Close connections on shutdown
    await app.state.db.close()
    await app.state.redis.aclose()

app = FastAPI(title="LLM Gateway", lifespan=lifespan)


# GET /health: checks that Postgres (with pgvector) and Redis are reachable.
@app.get('/health')

async def health():
    async with app.state.db.acquire() as conn:
        pgvector = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        redis_ok = await app.state.redis.ping()
        return {"status": "ok", "pgvector":pgvector, "redis":redis_ok}
