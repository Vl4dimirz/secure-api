"""PoC — invite-code single-use TOCTOU race (round 7 self-pentest).

Fires several registrations concurrently with the SAME single-use code and
different usernames. The consume path is check-then-act (SELECT used_at IS NULL
-> set used_at) with no atomic guard and no DB constraint on used_at, so the
reads interleave across await points and MORE THAN ONE registration succeeds =
multiple accounts minted from one single-use code (each a fresh AI-quota budget).
"""
import asyncio

from tests.conftest import seed_code


async def test_invite_code_single_use_race(client):
    await seed_code("RACE-CODE")

    async def reg(i: int) -> int:
        r = await client.post(
            "/auth/register",
            json={"username": f"racer{i}", "password": "supersecret1", "code": "RACE-CODE"},
        )
        return r.status_code

    results = await asyncio.gather(*[reg(i) for i in range(8)])
    successes = sum(1 for s in results if s == 201)
    print(f"\n[PoC] statuses from 8 concurrent registers on ONE code: {results}")
    print(f"[PoC] accounts created from ONE single-use code: {successes}")
    assert successes == 1, f"SINGLE-USE VIOLATED: {successes} accounts minted from one code"
