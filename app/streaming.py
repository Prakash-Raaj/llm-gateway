"""Turns our internal StreamChunks into OpenAI-style Server-Sent Events (SSE)."""

import json
import time
import uuid
from typing import AsyncIterator

from app.providers.base import ProviderError, StreamChunk
from app.schemas.openai import ChatCompletionChunk, ChoiceDelta, ChunkChoice, CompletionUsage


# Format one SSE event: "data: <payload>" followed by a blank line
def _sse(data: str) -> str:
    return f"data: {data}\n\n"


# Async generator: each `yield` sends one SSE event to the client right away.
# `first` is the chunk main.py already received (to catch early errors);
# `rest` is the provider's stream with the remaining chunks.
async def openai_sse(
        first: StreamChunk,
        rest: AsyncIterator[StreamChunk],
        model: str,
        include_usage: bool
)-> AsyncIterator[str]:

    chunk_id = f"chatcmpl-{uuid.uuid4().hex}" #same id + created for every chunk

    created = int(time.time())

    # Build one OpenAI chunk and wrap it as an SSE event (exclude_none drops empty fields)
    def make(choices, usage=None) -> str:
        chunk = ChatCompletionChunk(id=chunk_id, created=created, model=model, choices=choices, usage=usage)
        return _sse(chunk.model_dump_json(exclude_none=True))

    # First event announces the assistant role
    yield make([ChunkChoice(delta=ChoiceDelta(role="assistant", content=""))])


    # Put `first` back in front of the rest, so we can loop over everything at once
    async def all_chunks():
        yield first
        async for c in rest:
            yield c

    usage = None  # token counts, usually only on the provider's last chunk
    try:
        async for c in all_chunks():
            if c.delta:            # new text -> send it
                yield make([ChunkChoice(delta=ChoiceDelta(content=c.delta))])
            if c.finish_reason:    # model finished -> send empty delta + reason ("stop", "length")
                yield make([ChunkChoice(delta=ChoiceDelta(), finish_reason=c.finish_reason)])
            if c.usage:            # remember token counts for the end
                usage = c.usage

        # Optional final chunk with token counts (only if the client asked via stream_options)
        if include_usage and usage:
            yield make([], CompletionUsage(
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            ))
    except ProviderError as e:
        # Headers (200 OK) were already sent, so report the error inside the stream
        yield _sse(json.dumps({"error": {"message": str(e)}}))

    # Tells the client the stream is finished
    yield _sse("[DONE]")
