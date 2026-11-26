import pytest

from app.providers.base import BadRequestError, ChatRequest, Message, ProviderUnavailableError, RateLimitError
from app.providers.mock import MockProvider


@pytest.fixture
def req():
    return ChatRequest(model="m", messages=[Message(role="user", content="What is an LLm Gateway")])

async def test_chat_returns_reply_and_usage(req):
    res = await MockProvider(reply="hi there").chat(req)
    assert res.content == "hi there"
    assert res.usage.input_tokens == 5
    assert res.usage.output_tokens == 2

async def test_stream_rebuilds_full_reply(req):
    chunks = [c async for c in MockProvider(reply="one two three").stream(req)]
    assert "".join(c.delta for c in chunks) == "one two three"
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage is not None

@pytest.mark.parametrize(
    "error, expected",
    [
        ("rate_limit", RateLimitError),
        ("unavailable", ProviderUnavailableError),
        ("bad_request", BadRequestError),
    ],
)
async def test_error_rate_one_always_fails(req, error, expected):
    with pytest.raises(expected):
        await MockProvider(error_rate=1.0, error=error).chat(req)

def test_unknown_error_name_fails_test():
    with pytest.raises(KeyError):
        MockProvider(error="rate_limt")

