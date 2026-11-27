import os
import time
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.admin import router as admin_router
from app.auth import ApiKey
from app.config import load_config
from app.db import init_db
from app.providers.base import ChatRequest, Message, ProviderError, ProviderUnavailableError, RateLimitError, Usage
from app.providers.registry import build_providers
from app.ratelimit import RateLimiter, rate_limit
from app.schemas.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    CompletionUsage,
)
from app.streaming import openai_sse
from app.usage import UsageLogger, UsageRecord


# Runs on startup (before yield) and shutdown (after yield).
@asynccontextmanager
async def lifespan(app:FastAPI):
    # Open a reusable pool of Postgres connections and a Redis client
    app.state.db = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    await init_db(app.state.db)
    app.state.usage = UsageLogger(app.state.db)
    app.state.usage.start()
    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    app.state.limiter = RateLimiter(app.state.redis)
    app.state.config = load_config(os.environ.get("CONFIG_PATH", "config/models.yaml"))
    app.state.providers = build_providers(app.state.config)
    yield
    # Close connections on shutdown
    await app.state.usage.stop()
    await app.state.db.close()
    await app.state.redis.aclose()
    for p in app.state.providers.values():
        await p.aclose()

app = FastAPI(title="LLM Gateway", lifespan=lifespan)
app.include_router(admin_router)

# GET /health: checks that Postgres (with pgvector) and Redis are reachable.
@app.get('/health')

async def health():
    async with app.state.db.acquire() as conn:
        pgvector = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        redis_ok = await app.state.redis.ping()
        return {"status": "ok", "pgvector":pgvector, "redis":redis_ok}

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)

async def chat_completions(body: ChatCompletionRequest, api_key : ApiKey = Depends(rate_limit)):
    start = time.perf_counter()
    # Find which provider handles this model name
    route = app.state.config.models.get(body.model)

    # Queue one usage row (instant; written to postgres in the background)
    def record(status: int, usage: Usage|None = None, error: str | None = None)-> None:
        usage = usage or Usage()
        app.state.usage.log(UsageRecord(
            api_key_id= api_key.id,
            model= body.model, 
            provider= route.provider if route else None,
            provider_model=route.model if route else None,
            stream = body.stream,
            status_code=status,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            latency_ms=int((time.perf_counter()-start) * 1000),
            cost_usd=route.cost(usage.input_tokens, usage.output_tokens) if route else 0.0,
            error=error
        ))

    if route is None:
        record(404, error="unknown model")
        raise HTTPException(404, f"Unknown model '{body.model}'")
    provider = app.state.providers[route.provider]

    req = ChatRequest(
        model=route.model,   # provider's real model ID, not the client's name
        messages= [Message(**m.model_dump()) for m in body.messages],
        temperature=body.temperature,
        max_tokens=body.max_tokens
    )

    if body.stream:
        chunks = provider.stream(req)
        try:
            first = await anext(chunks)   # wait for the first chunk so early errors get a real status code
        except ProviderError as e:
            http_error = to_http_error(e)
            record(http_error.status_code, error=str(e))
            raise to_http_error(e) from e

        def on_finish(usage:Usage|None, error:ProviderError|None)-> None:
            if error is None:
                record(200, usage)
            else:
                record(to_http_error(error).status_code, usage, str(error))

        include_usage = bool(body.stream_options and body.stream_options.include_usage)
        return StreamingResponse(
            openai_sse(first, chunks, route.model, include_usage, on_finish),
            media_type="text/event-stream",
        )

    try:
        res = await provider.chat(req)
    except ProviderError as e:
        http_error = to_http_error(e)
        record(http_error.status_code, error=str(e))
        raise http_error from e

    record(200, res.usage)
    return ChatCompletionResponse(
        model=res.model,
        choices=[Choice(message=ChatMessage(role="assistant", content=res.content))],
        usage=CompletionUsage(
            prompt_tokens=res.usage.input_tokens,
            completion_tokens=res.usage.output_tokens,
            total_tokens=res.usage.input_tokens + res.usage.output_tokens,
        )
    )


# Map our provider errors to HTTP errors
def to_http_error(e: ProviderError) -> HTTPException:
    if isinstance(e, RateLimitError):
        return HTTPException(429, str(e))
    if isinstance(e, ProviderUnavailableError):
        return HTTPException(503, str(e))
    return HTTPException(400, str(e))
