import asyncio
import json

import pytest

from app.main import app

URL = "/v1/chat/completions"
BODY = {"model": "mock", "messages": [{"role": "user", "content": "Say hello"}]}


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# Usage rows are written in the background, so poll briefly until they appear
async def wait_for_usage(expected: int = 1):
    for _ in range(50):
        rows = await app.state.db.fetch("SELECT * FROM usage_logs ORDER BY id")
        if len(rows) >= expected:
            return rows
        await asyncio.sleep(0.05)
    raise AssertionError(f"expected {expected} usage rows, found {len(rows)}")


# --- Auth ---

async def test_missing_key_returns_401(client):
    res = await client.post(URL, json=BODY)
    assert res.status_code == 401


async def test_invalid_key_returns_401(client):
    res = await client.post(URL, json=BODY, headers=auth("gw_not_a_real_key"))
    assert res.status_code == 401

async def test_revoked_key_returns_401(client, api_key, admin_headers):
    res = await client.delete(f"/admin/keys/{api_key['id']}", headers=admin_headers)
    assert res.status_code == 200

    res = await client.post(URL, json=BODY, headers=auth(api_key["key"]))
    assert res.status_code == 401

async def test_normal_key_cannot_use_admin(client, api_key):
    res = await client.get("/admin/keys", headers=auth(api_key["key"]))
    assert res.status_code == 401


# --- Chat ---

async def test_chat_returns_openai_format_and_logs_usage(client, api_key):
    res = await client.post(URL, json=BODY, headers=auth(api_key["key"]))


    assert res.status_code == 200
    data = res.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "hello from mock"
    assert data["usage"] == {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}

    [row] = await wait_for_usage()

    assert row["api_key_id"] == api_key["id"]
    assert row["provider"] == "mock"
    assert row["status_code"] == 200
    assert row["stream"] is False
    assert float(row["cost_usd"]) == pytest.approx((2 * 1.0 + 3 * 2.0) / 1_000_000)


async def test_streaming_ends_with_done_and_logs_usage(client, api_key):
    body = {**BODY, "stream": True, "stream_options": {"include_usage": True}}
    res = await client.post(URL, json=body, headers=auth(api_key["key"]))

    assert res.status_code == 200
    data = [line.removeprefix("data: ") for line in res.text.splitlines() if line.startswith("data: ")]
    assert data[-1] == "[DONE]"
    chunks = [json.loads(d) for d in data[:-1]]
    text = "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks if c["choices"])
    assert text == "hello from mock"

    [row] = await wait_for_usage()
    assert row["stream"] is True
    assert row["status_code"] == 200
    assert row["completion_tokens"] == 3


# --- Errors ---

async def test_provider_rate_limit_returns_429_and_logs_it(client, api_key):
    res = await client.post(URL, json={**BODY, "model": "mock-fail"}, headers=auth(api_key["key"]))
    assert res.status_code == 429

    [row] = await wait_for_usage()
    assert row["status_code"] == 429
    assert "failure" in row["error"]


async def test_unknown_model_returns_404_and_logs_it(client, api_key):
    res = await client.post(URL, json={**BODY, "model": "nope"}, headers=auth(api_key["key"]))
    assert res.status_code == 404

    [row] = await wait_for_usage()
    assert row["status_code"] == 404
    assert row["provider"] is None
