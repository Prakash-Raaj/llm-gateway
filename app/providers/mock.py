"""Fake provider for tests: no network, configurable latency and errors."""

import asyncio
import random
from collections.abc import AsyncIterator

from app.providers.base import (
    BadRequestError,
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    StreamChunk,
    Usage,
)

# Map the `error` setting to the real error class
ERRORS: dict[str, type[ProviderError]] = {
    "rate_limit": RateLimitError,
    "unavailable": ProviderUnavailableError,
    "bad_request": BadRequestError,
}


class MockProvider(Provider):

    def __init__(
            self,
            name: str = "mock",
            latency_ms:int = 0,
            error_rate:float = 0.0,
            error: str = "rate_limit",
            reply: str = "Hello from the mock provider"
            ):

        self.name = name
        self.latency_ms = latency_ms
        self.error_rate = error_rate
        self.error = ERRORS[error]
        self.reply = reply

    # Sleep like a real provider, then maybe fail
    async def _simulate(self) -> None:
        await asyncio.sleep(self.latency_ms / 1000)
        if random.random() < self.error_rate:
            raise self.error(f"mock {self.name} failure")

    # Fake token count: 1 word = 1 token
    def _usage(self, req: ChatRequest) -> Usage:
        prompt_words = sum(len(m.content.split()) for m in req.messages)
        return Usage(input_tokens=prompt_words, output_tokens=len(self.reply.split()))

    async def chat(self, req: ChatRequest) -> ChatResponse:
        await self._simulate()
        return ChatResponse(
            content=self.reply, model=req.model, provider=self.name, usage=self._usage(req)
        )



    # Yield the reply word by word, then a final chunk with finish_reason + usage
    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]:
        await self._simulate()
        for i, word in enumerate(self.reply.split()):
            yield StreamChunk(delta=word if i == 0 else " " + word)
        yield StreamChunk(delta="", finish_reason="stop", usage=self._usage(req))