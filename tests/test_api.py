"""End-to-end API tests: health, auth flow, validation, ownership guards, rate limit."""
import pytest

from app.limits import limiter
from tests.conftest import make_token


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_register_returns_username(client):
    r = await client.post("/auth/register", json={"username": "alice", "password": "longenough1"})
    assert r.status_code == 201
    assert r.json() == {"username": "alice"}


async def test_duplicate_register_rejected(client):
    await client.post("/auth/register", json={"username": "bob", "password": "longenough1"})
    r = await client.post("/auth/register", json={"username": "bob", "password": "longenough1"})
    assert r.status_code == 400


async def test_short_password_is_422(client):
    r = await client.post("/auth/register", json={"username": "carol", "password": "short"})
    assert r.status_code == 422  # Pydantic min_length=8


async def test_login_wrong_password_is_401(client):
    await client.post("/auth/register", json={"username": "dave", "password": "longenough1"})
    r = await client.post("/auth/login", data={"username": "dave", "password": "wrongpass123"})
    assert r.status_code == 401


async def test_create_item_without_token_is_401(client):
    r = await client.post("/items", json={"title": "sneaky"})
    assert r.status_code == 401


async def test_create_item_with_token_then_list(client):
    token = await make_token(client)
    r = await client.post(
        "/items",
        json={"title": "Ship rung 6", "description": "tested"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Ship rung 6"
    assert body["id"] >= 1

    r2 = await client.get("/items")  # list is public
    assert r2.status_code == 200
    assert any(i["title"] == "Ship rung 6" for i in r2.json())


async def test_empty_title_is_422(client):
    token = await make_token(client)
    r = await client.post(
        "/items", json={"title": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422  # min_length=1


async def test_delete_item(client):
    token = await make_token(client)
    h = {"Authorization": f"Bearer {token}"}
    created = await client.post("/items", json={"title": "to delete"}, headers=h)
    item_id = created.json()["id"]
    r = await client.delete(f"/items/{item_id}", headers=h)
    assert r.status_code == 204
    r2 = await client.delete(f"/items/{item_id}", headers=h)  # already gone
    assert r2.status_code == 404


async def test_login_rate_limited_after_5(client):
    await client.post("/auth/register", json={"username": "eve", "password": "longenough1"})
    limiter.enabled = True  # off by default in the harness; on just for this test
    try:
        codes = []
        for _ in range(6):
            r = await client.post(
                "/auth/login", data={"username": "eve", "password": "longenough1"}
            )
            codes.append(r.status_code)
        assert 429 in codes  # the 6th within a minute must be throttled
    finally:
        limiter.enabled = False
