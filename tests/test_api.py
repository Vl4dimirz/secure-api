"""End-to-end API tests: health, invite gate, auth flow, validation, rate limit."""
from app.limits import limiter
from tests.conftest import make_token, seed_code


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_security_headers_present(client):
    r = await client.get("/health")
    for header in (
        "content-security-policy",
        "strict-transport-security",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
    ):
        assert r.headers.get(header), f"missing {header}"
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_register_returns_username(client):
    await seed_code("welcome-1")
    r = await client.post(
        "/auth/register",
        json={"username": "alice", "password": "longenough1", "code": "welcome-1"},
    )
    assert r.status_code == 201
    assert r.json() == {"username": "alice"}


async def test_register_without_code_is_422(client):
    r = await client.post(
        "/auth/register", json={"username": "noc", "password": "longenough1"}
    )
    assert r.status_code == 422  # code is a required field


async def test_register_unknown_code_is_403(client):
    r = await client.post(
        "/auth/register",
        json={"username": "intruder", "password": "longenough1", "code": "never-seeded"},
    )
    assert r.status_code == 403  # only owner-issued codes work


async def test_invite_code_is_single_use(client):
    await seed_code("one-shot")
    first = await client.post(
        "/auth/register",
        json={"username": "user_a", "password": "longenough1", "code": "one-shot"},
    )
    assert first.status_code == 201
    # Same code again -> refused; it was consumed, can't be shared/reused.
    second = await client.post(
        "/auth/register",
        json={"username": "user_b", "password": "longenough1", "code": "one-shot"},
    )
    assert second.status_code == 403


async def test_duplicate_username_does_not_consume_code(client):
    await seed_code("code-x")
    await seed_code("code-y")
    await client.post(
        "/auth/register",
        json={"username": "bob", "password": "longenough1", "code": "code-x"},
    )
    # Same username, different (still-valid) code -> 400 for the name, not 403.
    r = await client.post(
        "/auth/register",
        json={"username": "bob", "password": "longenough1", "code": "code-y"},
    )
    assert r.status_code == 400


async def test_short_password_is_422(client):
    await seed_code("pw-code")
    r = await client.post(
        "/auth/register",
        json={"username": "carol", "password": "short", "code": "pw-code"},
    )
    assert r.status_code == 422  # Pydantic min_length=8


async def test_login_wrong_password_is_401(client):
    await make_token(client, username="dave")
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

    # list is authed + scoped to the owner
    r2 = await client.get("/items", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert any(i["title"] == "Ship rung 6" for i in r2.json())


async def test_list_items_requires_auth(client):
    r = await client.get("/items")
    assert r.status_code == 401  # reads are no longer public


async def test_list_items_scoped_to_owner(client):
    alice = await make_token(client, username="alice")
    mallory = await make_token(client, username="mallory")
    await client.post(
        "/items", json={"title": "alice secret"},
        headers={"Authorization": f"Bearer {alice}"},
    )
    # mallory must not see alice's items
    r = await client.get("/items", headers={"Authorization": f"Bearer {mallory}"})
    assert r.status_code == 200
    assert all(i["title"] != "alice secret" for i in r.json())


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


async def test_cannot_delete_others_item(client):
    alice = await make_token(client, username="alice")
    mallory = await make_token(client, username="mallory")
    created = await client.post(
        "/items", json={"title": "alice private note"},
        headers={"Authorization": f"Bearer {alice}"},
    )
    item_id = created.json()["id"]
    # mallory must NOT be able to delete alice's item (IDOR / BOLA fix) -> 404
    r = await client.delete(f"/items/{item_id}", headers={"Authorization": f"Bearer {mallory}"})
    assert r.status_code == 404
    # ...but alice still can delete her own
    r2 = await client.delete(f"/items/{item_id}", headers={"Authorization": f"Bearer {alice}"})
    assert r2.status_code == 204


async def test_register_rate_limited_after_10(client):
    limiter.enabled = True  # off by default in the harness; on just for this test
    try:
        codes = []
        for _ in range(11):
            r = await client.post(
                "/auth/register",
                json={"username": "bruteforce", "password": "supersecret1", "code": "WRONG"},
            )
            codes.append(r.status_code)
        assert 429 in codes  # brute-forcing /register is throttled
    finally:
        limiter.enabled = False


async def test_login_rate_limited_after_5(client):
    await make_token(client, username="eve")
    limiter.enabled = True  # off by default in the harness; on just for this test
    try:
        codes = []
        for _ in range(6):
            r = await client.post(
                "/auth/login", data={"username": "eve", "password": "supersecret1"}
            )
            codes.append(r.status_code)
        assert 429 in codes  # the 6th within a minute must be throttled
    finally:
        limiter.enabled = False
