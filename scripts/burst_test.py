"""Burst test: fire many requests at once and check that only `rpm_limit` of them get through."""

import asyncio
import os
from collections import Counter

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"
ADMIN = {"Authorization": f"Bearer {os.environ['ADMIN_API_KEY']}"}
LIMIT = 10   # rpm for the temporary test key
BURST = 50  # requests sent at the same moment
BODY = {"model": "mock", "messages": [{"role": "user", "content": "hi"}]}

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # A fresh key with a low limit, so your real key's bucket isn't touched
        res = await client.post("/admin/keys", json={"name": "burst-test", "rpm_limit": LIMIT}, headers=ADMIN)
        res.raise_for_status()
        key = res.json()
        headers = {"Authorization": f"Bearer {key['key']}"}

        try:
            # Fire all requests at the same moment
            responses = await asyncio.gather(
                *[client.post("/v1/chat/completions", json=BODY, headers=headers) for _ in range(BURST)]
            )
        finally:
            # Clean up: revoke the temporary key even if something failed
            await client.delete(f"/admin/keys/{key['id']}", headers=ADMIN)

    counts = Counter(r.status_code for r in responses)
    print(f"Sent {BURST} requests at once (limit: {LIMIT} rpm)")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")

    limited = [r for r in responses if r.status_code == 429]
    if limited:
        h = limited[0].headers
        print(f"Retry-After: {h['Retry-After']}s, X-RateLimit-Limit: {h['X-RateLimit-Limit']}")

    passed = counts[200] == LIMIT and counts[429] == BURST - LIMIT
    print("PASS ✅" if passed else "FAIL ❌")


asyncio.run(main())