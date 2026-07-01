"""AI endpoint security tests — the guards work with NO real API key needed."""
import asyncio

from sqlalchemy import update

from app.config import settings
from app.models import User
from tests.conftest import TestSession, make_token, set_ai_used


async def test_quota_reserve_is_race_safe(client):
    # Fire many concurrent atomic reserves (the exact UPDATE the AI route uses)
    # and confirm the cap is never exceeded — no TOCTOU over-grant.
    await make_token(client, username="racer")  # ai_calls_used starts at 0
    quota = settings.ai_call_quota

    async def reserve() -> int:
        async with TestSession() as s:
            r = await s.execute(
                update(User)
                .where(User.username == "racer", User.ai_calls_used < quota)
                .values(ai_calls_used=User.ai_calls_used + 1)
            )
            await s.commit()
            return r.rowcount

    granted = sum(await asyncio.gather(*[reserve() for _ in range(quota + 15)]))
    assert granted == quota  # exactly the cap, never more


async def test_ai_requires_auth(client):
    r = await client.post("/ai/summarize", json={"text": "some text to summarize"})
    assert r.status_code == 401  # no anonymous access to a paid model


async def test_ai_rejects_empty_text(client):
    token = await make_token(client)
    r = await client.post(
        "/ai/summarize", json={"text": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422  # schema min_length=1


async def test_ai_rejects_oversized_text(client):
    token = await make_token(client)
    r = await client.post(
        "/ai/summarize",
        json={"text": "x" * 7000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422  # schema max_length=6000 caps token cost


async def test_ai_quota_exhausted_is_429(client):
    token = await make_token(client, username="not")
    await set_ai_used("not", settings.ai_call_quota)  # spend the whole trial budget
    r = await client.post(
        "/ai/summarize",
        json={"text": "please summarize this"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 429  # refused before ever calling the paid model


async def test_ai_503_when_key_missing(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    token = await make_token(client)
    r = await client.post(
        "/ai/summarize",
        json={"text": "please summarize this"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503  # configured cleanly, never a 500 crash
