import json

import httpx

from app.providers.base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderUnavailableError,
    StreamChunk,
    Usage,
    raise_for_status,
)


# Works for any provider with an OpenAI-style API (Groq, Gemini, OpenRouter, ...)
class OpenAICompatibleProvider(Provider):

    def __init__(self, name: str, base_url: str, api_key: str):
        super().__init__()
        self.name = name
        self.client = httpx.AsyncClient(
            base_url= base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
        )


    # Build the OpenAI-style request body (shared by chat and stream)
    def _payload(self, req: ChatRequest) -> dict:
        payload = {"model": req.model, "messages": [m.model_dump() for m in req.messages]}
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        return payload 
    
    async def chat(self, req: ChatRequest) -> ChatResponse:
        payload = self._payload(req)

        try:
            r = await self.client.post("/chat/completions", json=payload)
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"{self.name} unreachable: {e}") from e

        raise_for_status(r)

    # Response is already sent in openAI format
        data = r.json()
        usage = data.get("usage") or {}
        return ChatResponse(
            content = data["choices"][0]["message"]["content"] or "",
            model=data.get("model", req.model),
            provider = self.name,
            usage = Usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0)
            )
        )
    async def stream(self, req: ChatRequest):
        payload = self._payload(req)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}

        try:
            async with self.client.stream("POST", "/chat/completions", json=payload) as r:
                if r.status_code>=400:
                    await r.aread()
                    raise_for_status(r)
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line.removeprefix("data:").strip()
                    if data_str == "[DONE]":
                        break

                    data = json.loads(data_str)
                    choice = data["choices"][0] if data.get("choices") else {}
                    usage = data.get("usage") or (data.get("x_groq") or {}).get("usage")

                    yield StreamChunk(
                        delta = (choice.get("delta") or {}).get("content") or "",
                        finish_reason=choice.get("finish_reason"),
                        usage=Usage(
                            input_tokens=usage.get("prompt_tokens", 0),
                            output_tokens=usage.get("completion_tokens", 0)
                        ) if usage else None
                    )
                
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"{self.name} unreachable: {e}") from e


    async def aclose(self):
        await self.client.aclose()
