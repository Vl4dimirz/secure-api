"""AI endpoint security tests — the guards work with NO real API key needed."""
from app.config import settings
from tests.conftest import make_token


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


async def test_ai_503_when_key_missing(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    token = await make_token(client)
    r = await client.post(
        "/ai/summarize",
        json={"text": "please summarize this"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503  # configured cleanly, never a 500 crash
