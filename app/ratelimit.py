"""Token bucket rate limiter, one bucket per API key, stored in Redis."""
import logging
import math

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from redis.exceptions import RedisError

from app.auth import ApiKey, require_api_key

log = logging.getLogger(__name__)

# Runs inside Redis as one atomic step, so concurrent requests can't race.
# KEYS[1] = bucket key, ARGV[1] = capacity (max tokens), ARGV[2] = refill rate (tokens per ms)
TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])

-- Current time from Redis itself, in milliseconds
local t = redis.call("TIME")
local now = t[1] * 1000 + math.floor(t[2] / 1000)

-- Load the bucket; a new key starts full
local bucket = redis.call("HMGET", KEYS[1], "tokens", "ts")
local tokens = tonumber(bucket[1]) or capacity
local ts = tonumber(bucket[2]) or now

-- Add the tokens earned since the last request, capped at capacity
tokens = math.min(capacity, tokens + (now - ts) * rate)

-- Spend one token if we have it; otherwise work out when the next one arrives
local allowed = 0
local retry_ms = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_ms = math.ceil((1 - tokens) / rate)
end

-- Save the bucket; delete it once it would be full again anyway
redis.call("HSET", KEYS[1], "tokens", tokens, "ts", now)
redis.call("PEXPIRE", KEYS[1], math.ceil(capacity / rate))

return {allowed, math.floor(tokens), retry_ms}
"""


class RateLimitResult(BaseModel):
    allowed: bool
    remaining: int       # whole tokens left after this request
    retry_after_ms: int  # 0 if allowed


class RateLimiter:

    def __init__(self, redis):
        # Loads the script into Redis once; later calls send only its hash (EVALSHA)
        self.script = redis.register_script(TOKEN_BUCKET_LUA)

     # Try to take one token from this key's bucket
    async def hit(self, key_id: int, rpm: int)-> RateLimitResult:
        allowed, remaining, retry_ms = await self.script(
            keys = [f"ratelimit:{key_id}"],
            args = [rpm, rpm/60_000] # refill tokens every 60,000 ms
        )
        return RateLimitResult(allowed=bool(allowed), remaining=remaining, retry_after_ms=retry_ms)


# Dependency for limited routes: a valid key (checked first) plus a token from its bucket

async def rate_limit(request: Request, api_key: ApiKey = Depends(require_api_key))-> ApiKey:
    try:
        result = await request.app.state.limiter.hit(api_key.id, api_key.rpm_limit)
    except RedisError:
        # Fail open: if Redis is down, serve the request rather than block everyone
        log.exception("Rate limiter unavailable; allowing request")
        return api_key

    if not result.allowed:
        raise HTTPException(
            429,
            f"Rate limit exceeded: {api_key.rpm_limit} requests per minute",
            headers={
                "Retry-After": str(math.ceil(result.retry_after_ms / 1000)),  # seconds
                "X-RateLimit-Limit": str(api_key.rpm_limit),
                "X-RateLimit-Remaining": "0",
            }
        )
    return api_key