import json

from app.providers.base import RateLimitError, StreamChunk, Usage
from app.streaming import openai_sse


# Turn raw SSE text into a list of payloads (strings after "data: ")
def parse(events: list[str]) -> list[str]:
    return [e.removeprefix("data: ").strip() for e in events]


# Fake provider stream; optionally fails after the chunks
async def fake_stream(chunks, fail=False):
    for c in chunks:
        yield c
    if fail:
        raise RateLimitError("boom")

# Run openai_sse and record every on_finish call
async def run(first, rest, include_usage=False):
    calls = []
    events = [
        e async for e in openai_sse(
            first, rest, "test-model", include_usage, 
            on_finish=lambda usage, error:calls.append((usage, error))
        )
    ]
    return parse(events), calls


async def test_stream_format_and_on_finish():
    usage = Usage(input_tokens=3, output_tokens=2)
    first = StreamChunk(delta="Hello")
    rest = fake_stream([StreamChunk(delta=" world", finish_reason="stop", usage=usage)])

    data, calls = await run(first, rest, include_usage=True)

    assert data[-1] == "[DONE]"
    chunks = [json.loads(d) for d in data[:-1]]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"])
    assert text == "Hello world"
    assert chunks[-1]["usage"]["total_tokens"] == 5
    assert calls == [(usage, None)]


async def test_mid_stream_error_is_reported():
    data, calls = await run(StreamChunk(delta="Hi"), fake_stream([], fail=True))

    assert data[-1] == "[DONE]"
    assert json.loads(data[-2])["error"]["message"] == "boom"
    usage, error = calls[0]
    assert isinstance(error, RateLimitError)