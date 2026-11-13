"""Common interface that every LLM provider (Ollama, Groq, Gemini, ...) must follow."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal

from pydantic import BaseModel


# --- Shared request/response types (same shape for every provider) ---

# One message in a conversation
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


# What the router sends to a provider
class ChatRequest(BaseModel):
    model: str                         # the provider's real model ID
    messages: list[Message]
    temperature: float | None = None   # None = use provider default
    max_tokens: int | None = None


# Token counts, used for usage logging and cost
class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


# Full (non-streaming) reply
class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: Usage


# One piece of a streaming reply
class StreamChunk(BaseModel):
    delta: str                          # new text in this chunk
    finish_reason: str | None = None    # set only on the last chunk
    usage: Usage | None = None          # usually only on the last chunk


# Result of turning texts into vectors (for pgvector later)
class EmbedResponse(BaseModel):
    embeddings: list[list[float]]       # one vector per input text
    model: str
    usage: Usage


# --- Errors: tell the router WHY a call failed so it can decide what to do ---

class ProviderError(Exception):
    """Base class for all provider errors."""


class RateLimitError(ProviderError):
    """429 from provider -> try another provider."""


class ProviderUnavailableError(ProviderError):
    """5xx or timeout -> try another provider."""


class BadRequestError(ProviderError):
    """400 (bad input) -> don't retry, return error to client."""


# --- The interface every provider implements ---

class Provider(ABC):
    name: str                           # e.g. "groq", "ollama"
    supports_embeddings: bool = False   # router skips providers that can't embed

    # Send messages, wait, and get the whole answer back at once
    @abstractmethod
    async def chat(self, req: ChatRequest) -> ChatResponse: ...

    # Send messages and get the answer piece by piece as it's generated.
    # Implement as `async def stream(...)` that uses `yield StreamChunk(...)`.
    @abstractmethod
    def stream(self, req: ChatRequest) -> AsyncIterator[StreamChunk]: ...

    # Turn texts into embedding vectors (optional; override if supported)
    async def embed(self, texts: list[str], model: str) -> EmbedResponse:
        raise NotImplementedError(f"{self.name} does not support embeddings")
