import httpx

from app.providers.base import (
    raise_for_status, ChatRequest, ChatResponse, Provider, ProviderUnavailableError, Usage,
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

    async def chat(self, req: ChatRequest) -> ChatResponse:
        payload = {"model":req.model, "messages" : [m.model_dump() for m in req.messages]}
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens

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
    def stream(self, req):
        raise NotImplementedError("Streaming not implemented yet")

    async def aclose(self):
        await self.client.aclose()
