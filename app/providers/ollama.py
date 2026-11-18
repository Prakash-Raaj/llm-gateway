import httpx
import json

from app.providers.base import (
    BadRequestError, ChatRequest, ChatResponse, Provider,
    ProviderUnavailableError, RateLimitError, Usage, raise_for_status, StreamChunk
)


class OllamaProvider(Provider):

    name = "ollama"

    def __init__(self, base_url: str):
        # One reusable HTTP client; long timeout because local models can be slow
        self.client = httpx.AsyncClient(base_url=base_url, timeout=120)

    # Translate ChatRequest -> Ollama /api/chat -> ChatResponse

    def _payload(self, req: ChatRequest, stream: bool) -> dict:
        options = {"temperature": req.temperature, "num_predict": req.max_tokens}
        return {
            "model": req.model,
            "messages": [m.model_dump() for m in req.messages],
            "stream": stream,
            "options": {k: v for k, v in options.items() if v is not None},
        }

    async def chat(self, req:ChatRequest) -> ChatResponse:

        payload = self._payload(req, stream=False)

        try:
            r = await self.client.post("/api/chat", json=payload)
        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"Ollama unreachable: {e}") from e

        raise_for_status(r)

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
    
    # Read Ollama's line-by-line JSON and yield StreamChunks
    async def stream(self, req:ChatRequest):
        try:
            async with self.client.stream("POST", "/api/chat", json=self._payload(req, stream=True)) as r:
                if r.status_code >=400:
                    await r.aread() # load the error body so raise_for_status can read it
                    raise_for_status(r)
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)

                    if data.get("done"):
                        yield StreamChunk(
                            delta="",
                            finish_reason=data.get("done_reason", "stop"),
                            usage=Usage(
                                input_tokens=data.get("prompt_eval_count", 0),
                                output_tokens=data.get("eval_count", 0),
                            )
                        )
                    else:
                        yield StreamChunk(delta=data["message"]["content"])

        except httpx.RequestError as e:
            raise ProviderUnavailableError(f"Ollama unreachable: {e}") from e

    async def aclose(self):
        await self.client.aclose()