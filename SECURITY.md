# Security

This document describes the security posture of Secure API: the controls that are
built in, the results of an adversarial self-review (a mini penetration test the
project was run against), and how to report a vulnerability.

The guiding principle of this project is simple: **do not assume a control works
until you have tried to break it and failed.** Every finding below was proven with
a working proof-of-concept, fixed, and locked in with an automated regression test.

---

## Security controls

| Area | Control |
|------|---------|
| Authentication | Signed JWTs (HS256, `exp` enforced); passwords hashed with bcrypt (salted), never stored or logged in plaintext |
| Login hardening | Constant-time password check (bcrypt runs even for unknown usernames — no timing oracle); rate limited (5/min) |
| Registration | Invite-only, **single-use** codes, **fail-closed** (no codes configured = registration disabled); rate limited (10/min) |
| Authorization | Per-object ownership — a user can only read or delete their own items (no cross-user access) |
| AI endpoint | Requires a JWT; per-account call quota enforced with an **atomic** reserve (no race); input length capped; provider errors never leaked to the client |
| Admin API | Separate operator token, constant-time comparison, fail-closed, rate limited; the token check runs after the rate limiter so it can't be brute-forced |
| Input validation | Pydantic v2 schemas on every request; oversized/empty input rejected at the edge |
| Injection | SQLAlchemy parameterized queries throughout — no string-built SQL |
| Secrets | Read from environment only; **the app refuses to boot in production while the JWT secret is still the repo default** |
| Transport/runtime | Multi-stage Docker image runs as a non-root user |
| Schema changes | Alembic migrations — no destructive rebuilds |

---

## Self-assessment (penetration test findings)

The API was attacked against itself across several rounds. All findings are fixed
and covered by tests in `tests/`.

| # | Finding | OWASP API | Severity | Status |
|---|---------|-----------|----------|--------|
| 1 | **JWT forgery via default secret** — the dev `SECRET_KEY` lives in the public repo; a deploy that forgot to override it let anyone forge a valid token for any user (no account, no invite code) = full auth bypass. | API2 Broken Authentication | Critical | Fixed — production refuses to start while the secret is the default |
| 2 | `alg=none` token forgery | API2 | — | Not vulnerable — decoding pins `algorithms=["HS256"]` |
| 3 | **IDOR on delete** — any authenticated user could delete any other user's item. | API1 BOLA | High | Fixed — items have an owner; delete returns 404 unless you own it |
| 4 | **Excessive data exposure** — `GET /items` was world-readable; anyone (even anonymous) could read every user's data. | API1 / API3 | High | Fixed — reads require auth and are scoped to the owner |
| 5 | **No rate limit on registration** — invite-code brute-force / username enumeration. | API4 Resource Consumption | High | Fixed — `10/min` |
| 6 | **Admin token brute-force** — `/admin/*` had no rate limit, and the token check ran before any limiter could count guesses. | API2 / API4 | Medium | Fixed — check moved into the handler so the limiter fires first; `10/min` |
| 7 | **Login timing oracle** — a missing user skipped bcrypt, so response time revealed which usernames exist. | API2 | Medium | Fixed — bcrypt runs against a dummy hash for unknown users |
| 8 | **AI quota race (TOCTOU)** — concurrent requests could read-check-then-increment past the per-account cap. | API4 | Medium | Fixed — single atomic `UPDATE ... WHERE used < quota` with refund on failure |
| 9 | **bcrypt truncation** — password max length exceeded bcrypt's 72-byte limit (silent truncation). | Cryptographic hygiene | Low | Fixed — capped at 72 |

Verification: every fix has a regression test (`pytest`), and the exploitable ones
were reproduced with a live proof-of-concept before and after the fix (forged token
-> 401, cross-user delete -> 404, anonymous list -> 401, register/admin floods ->
429, login timing evened out, concurrent quota reserve grants exactly the cap).

---

## Threat model and known limitations

In scope: the HTTP API surface — authentication, authorization, input handling,
rate limiting, and abuse of the paid AI endpoint.

Known, accepted limitations (documented rather than hidden):

- **No token revocation.** JWTs are valid until they expire (30 min default); there
  is no server-side blacklist. Keep the expiry short; add a deny-list if needed.
- **Rate-limit store is in-memory.** Fine for a single instance; use a shared store
  (e.g. Redis) if you run multiple replicas.
- **Registration reveals username-taken** (`400`) vs an invalid code (`403`). With
  single-use invite codes this yields at most one probe per code.

---

## Reporting a vulnerability

If you find a security issue, please do not open a public issue. Email the
maintainer with steps to reproduce and allow reasonable time for a fix before any
public disclosure. Responsible reports are welcome and appreciated.
