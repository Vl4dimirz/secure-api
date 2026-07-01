"""Admin API tests — issuing/listing/revoking invite codes, and its gate."""
from app.config import settings
from tests.conftest import ADMIN_HEADERS


async def test_admin_requires_token(client):
    r = await client.post("/admin/invite-codes", json={"count": 2})
    assert r.status_code == 403  # no/invalid admin token


async def test_admin_wrong_token_is_403(client):
    r = await client.post(
        "/admin/invite-codes", json={"count": 1}, headers={"X-Admin-Token": "nope"}
    )
    assert r.status_code == 403


async def test_admin_generate_and_list(client):
    r = await client.post("/admin/invite-codes", json={"count": 3, "prefix": "TEST"}, headers=ADMIN_HEADERS)
    assert r.status_code == 201
    created = r.json()["created"]
    assert len(created) == 3
    assert all(c.startswith("TEST-") for c in created)

    listed = await client.get("/admin/invite-codes", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    codes = {row["code"] for row in listed.json()}
    assert set(created) <= codes


async def test_admin_issued_code_actually_registers(client):
    r = await client.post("/admin/invite-codes", json={"count": 1}, headers=ADMIN_HEADERS)
    code = r.json()["created"][0]
    reg = await client.post(
        "/auth/register",
        json={"username": "issued_user", "password": "supersecret1", "code": code},
    )
    assert reg.status_code == 201  # admin-issued code works end-to-end


async def test_admin_revoke_unused_code(client):
    code = (await client.post("/admin/invite-codes", json={"count": 1}, headers=ADMIN_HEADERS)).json()["created"][0]
    revoked = await client.delete(f"/admin/invite-codes/{code}", headers=ADMIN_HEADERS)
    assert revoked.status_code == 204
    # Once revoked, it can't be used to register.
    reg = await client.post(
        "/auth/register",
        json={"username": "toolate", "password": "supersecret1", "code": code},
    )
    assert reg.status_code == 403


async def test_admin_503_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    r = await client.post("/admin/invite-codes", json={"count": 1}, headers=ADMIN_HEADERS)
    assert r.status_code == 503  # fail-closed when no admin token is set
