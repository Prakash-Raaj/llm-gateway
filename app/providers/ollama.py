import httpx

from app.providers.base import (
    BadRequestError, ChatRequest, ChatResponse, Provider,
    ProviderUnavailableError, RateLimitError, Usage,
)


class OllamaProvider(Provider):

    name = "ollama"

    def __init__(self, base_url: str):
        # One reusable HTTP client; long timeout because local models can be slow
        self.client = httpx.AsyncClient(base_url=base_url, timeout=120)

    # Translate ChatRequest -> Ollama /api/chat -> ChatResponse

    async def chat(self, req:ChatRequest) -> ChatResponse:
        options = {"temperature":req.temperature, "num_predict": req.max_tokens}

        payload = {
            "model":req.model,
            "messages": [m.model_dump() for m in req.messages],
            "stream": False,
            "options": {k:v for k, v in options.items() if v is not None}
        }

        try:
            r = await self.client.post("/api/chat", json=payload)
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"Ollama unreachable: {e}") from e

        # Map HTTP status codes to our error types
        if r.status_code == 429:
            raise RateLimitError(r.text)
        if r.status_code >= 500:
            raise ProviderUnavailableError(r.text)
        if r.status_code >= 400:
            raise BadRequestError(r.text)  # e.g. model not found

        data = r.json()
        return ChatResponse(
            content=data["message"]["content"],
            model=data["model"],
            provider=self.name,
            usage= Usage(
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )
        )
    
      # Required by the interface; implemented later
    def stream(self, req):
        raise NotImplementedError("Streaming not implemented yet")

    async def aclose(self):
        await self.client.aclose()