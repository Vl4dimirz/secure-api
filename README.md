# Secure API — a production-minded FastAPI backend

A small, complete backend built the way a real service should be: authentication,
password hashing, rate limiting, a real database, an automated test suite, a
hardened container image, and an authed AI endpoint. Each piece is a deliberate
security decision, not an afterthought.

Built with **FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · JWT · bcrypt · Docker**.

> **[SECURITY.md](SECURITY.md)** — the controls, a self-penetration-test findings
> table (each vuln proven, fixed, and regression-tested), and how to report an issue.

---

## Why this exists

Most "FastAPI example" repos stop at a CRUD route with data in a Python dict. This
one is built as a ladder of production concerns — every rung is a layer of defense
that a live API actually needs:

| Layer | What it does | Why it matters (security) |
|------:|--------------|---------------------------|
| **Validation** | Pydantic v2 models on every input | Rejects malformed/oversized input at the edge |
| **Invite-only sign-up** | Owner-issued, single-use codes, fail-closed | No self-service accounts; a leaked code works exactly once |
| **JWT auth** | Bearer tokens, `get_current_user` dependency | Only authenticated callers reach protected routes |
| **Password hashing** | bcrypt, never plaintext | A DB leak doesn't expose passwords |
| **Rate limiting** | slowapi, `5/min` on login | Blunts credential brute-force |
| **Real database** | SQLAlchemy async, SQLite → Postgres by URL | Persistence + parameterized queries (no string SQL) |
| **Tests** | 18 pytest cases, isolated in-memory DB | Guards every layer against regressions |
| **Migrations** | Alembic, auto-applied on startup | Schema evolves without wiping data |
| **Container** | Multi-stage image, runs as non-root | Smaller attack surface, no root in the container |
| **Per-account AI quota** | N calls per account, then cut off | A shared/leaked login still can't drain the token budget |
| **AI endpoint** | Authed, rate-limited, cost-capped Claude bridge | An LLM is a paid, abusable resource — treat it like one |

The application code is database-agnostic: it runs on SQLite locally and on real
**PostgreSQL** in Docker **without a single code change** — only `DATABASE_URL` differs.

---

## Endpoints

| Method | Path | Auth | Notes |
|-------:|------|:----:|-------|
| `GET` | `/health` | — | Liveness/readiness probe |
| `POST` | `/auth/register` | 🔑 code | Create a user (bcrypt-hashed) · requires an owner-issued **single-use** invite code |
| `POST` | `/auth/login` | — | Returns a JWT · rate-limited `5/min` |
| `GET` | `/items` | — | List items (public read) |
| `POST` | `/items` | ✅ | Create an item |
| `DELETE` | `/items/{id}` | ✅ | Delete an item |
| `POST` | `/ai/summarize` | ✅ | Summarize text via Claude · rate-limited `10/min` · input capped · per-account quota |
| `POST` | `/admin/invite-codes` | 🛡️ admin | Generate N single-use invite codes |
| `GET` | `/admin/invite-codes` | 🛡️ admin | List codes with used/unused status |
| `DELETE` | `/admin/invite-codes/{code}` | 🛡️ admin | Revoke an unused code |

`✅` = user JWT · `🔑 code` = invite code · `🛡️ admin` = `X-Admin-Token` header.

Interactive docs at `/docs` (Swagger) when running.

---

## Run it

### Local (SQLite)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt   # runtime + test deps
.venv\Scripts\uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

### Docker (real PostgreSQL, one command)

```bash
docker compose up --build
# API on http://localhost:8000, backed by a Postgres container
```

The same image runs on Postgres purely by swapping `DATABASE_URL` — that switch is
already wired in `docker-compose.yml`.

### Database migrations (Alembic)

The schema is managed by **Alembic migrations**, applied automatically on startup —
so both local and Docker "just work" on a fresh database, and a schema change never
means wiping data. To evolve the schema, edit the models then:

```bash
.venv\Scripts\alembic revision --autogenerate -m "describe the change"
.venv\Scripts\alembic upgrade head     # also runs automatically when the app starts
```

Existing rows are preserved (it's an `ALTER`, not a drop-and-recreate) — no more
`docker compose down -v`.

### Tests

```bash
.venv\Scripts\pytest      # 18 passed
```

---

## Configuration

Copy `.env.example` to `.env` and fill in real values (never commit `.env`):

```env
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(48))">
DATABASE_URL=sqlite+aiosqlite:///./app.db
# Comma-separated, single-use invite codes — issue one per user; empty = closed.
REGISTRATION_CODE=CODE-ONE,CODE-TWO,CODE-THREE
AI_CALL_QUOTA=10   # AI calls allowed per account before it's cut off
ADMIN_TOKEN=<long random token — enables /admin/*; empty = admin API disabled>
ANTHROPIC_API_KEY=<your Anthropic key — enables /ai/summarize, else it returns 503>
```

Sign-up is **invite-only, single-use, and fail-closed**: `/auth/register` accepts a
code from `REGISTRATION_CODE` exactly once (it's consumed on use), so a leaked code
can't be reshared to mint accounts. Each account then gets `AI_CALL_QUOTA` AI calls
before it's cut off — so even a shared login can't run up your bill. No codes set =
registration disabled entirely.

Secrets are read from the environment only — nothing sensitive is hardcoded, and
`.env` is git-ignored.

---

## Project layout

```
app/
  main.py         # app wiring: lifespan (DB init), rate limiter, routers
  config.py       # env-driven settings (pydantic-settings)
  database.py     # async engine, session, get_db dependency
  models.py       # SQLAlchemy ORM tables (User, Item, InviteCode)
  schemas.py      # Pydantic request/response models
  auth.py         # bcrypt hashing, JWT, get_current_user
  limits.py       # slowapi rate limiter
  routers/        # auth, items, ai
alembic/          # migration scripts (versions/) + env.py
tests/            # pytest suite (isolated in-memory DB)
Dockerfile        # multi-stage, non-root
docker-compose.yml# api + postgres
```
