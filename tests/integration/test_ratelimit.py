import asyncio

import pytest
import redis.asyncio as redis

from app.ratelimit import RateLimiter


@pytest.fixture
async def limiter(redis_url):
    client = redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()  # empty buckets so every test starts clean
    yield RateLimiter(client)
    await client.aclose()


async def test_allows_up_to_the_limit_then_blocks(limiter):
    results = [await limiter.hit(key_id=1, rpm=5) for _ in range(6)]

    assert [r.allowed for r in results] == [True] * 5 + [False]
    assert [r.remaining for r in results[:5]] == [4, 3, 2, 1, 0]
    assert results[-1].retry_after_ms > 0


async def test_each_key_has_its_own_bucket(limiter):
    for _ in range(3):
        await limiter.hit(key_id=1, rpm=3)

    assert (await limiter.hit(key_id=1, rpm=3)).allowed is False
    assert (await limiter.hit(key_id=2, rpm=3)).allowed is True

async def test_tokens_refill_over_time(limiter):
    # 120 rpm = 2 per second = 1 token every 500 ms
    for _ in range(120):
        await limiter.hit(key_id=1, rpm=120)
    assert (await limiter.hit(key_id=1, rpm=120)).allowed is False

    await asyncio.sleep(0.6)
    assert (await limiter.hit(key_id=1, rpm=120)).allowed is True


async def test_concurrent_burst_never_exceeds_limit(limiter):
    # 50 requests at the same moment against a limit of 10
    results = await asyncio.gather(*[limiter.hit(key_id=1, rpm=10) for _ in range(50)])
    assert sum(r.allowed for r in results) == 10


async def test_reset_time_grows_as_bucket_empties(limiter):
    # 60 rpm = 1 token per second, so each used token adds ~1 s until full
    first = await limiter.hit(key_id=1, rpm=60)
    for _ in range(9):
        last = await limiter.hit(key_id=1, rpm=60)

    assert 900 <= first.reset_ms <= 1000
    assert 9_000 <= last.reset_ms <= 10_000