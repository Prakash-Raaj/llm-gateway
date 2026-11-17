import os
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException

from app.providers.base import (
    BadRequestError, ChatRequest, Message, ProviderUnavailableError, RateLimitError,
)
from app.providers.ollama import OllamaProvider
from app.schemas.openai import (
    ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Choice, CompletionUsage,
)


# Runs on startup (before yield) and shutdown (after yield).
@asynccontextmanager
async def lifespan(app:FastAPI):
    # Open a reusable pool of Postgres connections and a Redis client
    app.state.db = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    app.state.ollama = OllamaProvider(os.environ["OLLAMA_BASE_URL"])
    yield
    # Close connections on shutdown
    await app.state.db.close()
    await app.state.redis.aclose()
    await app.state.ollama.aclose()

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

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)

async def chat_completions(body: ChatCompletionRequest):

    if body.stream:
        raise HTTPException(400, "Streaming not supported yet")

    req = ChatRequest(
        model=body.model,
        messages= [Message(**m.model_dump()) for m in body.messages],
        temperature=body.temperature,
        max_tokens=body.max_tokens
    )

    try:
        res = await app.state.ollama.chat(req)
    except RateLimitError as e:
        raise HTTPException(429, str(e))
    except ProviderUnavailableError as e:
        raise HTTPException(503, str(e))
    except BadRequestError as e:
        raise HTTPException(400, str(e))

    return ChatCompletionResponse(
        model=res.model,
        choices=[Choice(message=ChatMessage(role="assistant", content=res.content))],
        usage=CompletionUsage(
            prompt_tokens=res.usage.input_tokens,
            completion_tokens=res.usage.output_tokens,
            total_tokens=res.usage.input_tokens + res.usage.output_tokens,
        )
    )