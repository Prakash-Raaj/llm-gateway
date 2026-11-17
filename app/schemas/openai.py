import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field


# Request 
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content:str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False

# Respose

class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str | None = "stop"


class CompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")  # unique ID per reply
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))          # Unix timestamp
    model: str
    choices: list[Choice]
    usage: CompletionUsage