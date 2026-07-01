# Secure API — a production-minded FastAPI backend

A small, complete backend built the way a real service should be: authentication,
password hashing, rate limiting, a real database, an automated test suite, a
hardened container image, and an authed AI endpoint. Each piece is a deliberate
security decision, not an afterthought.

Built with **FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · JWT · bcrypt · Docker**.

---

## Why this exists

Most "FastAPI example" repos stop at a CRUD route with data in a Python dict. This
one is built as a ladder of production concerns — every rung is a layer of defense
that a live API actually needs:

| Layer | What it does | Why it matters (security) |
|------:|--------------|---------------------------|
| **Validation** | Pydantic v2 models on every input | Rejects malformed/oversized input at the edge |
| **Invite-only sign-up** | Owner-issued code, fail-closed | No self-service accounts → nobody can burn the paid AI budget |
| **JWT auth** | Bearer tokens, `get_current_user` dependency | Only authenticated callers reach protected routes |
| **Password hashing** | bcrypt, never plaintext | A DB leak doesn't expose passwords |
| **Rate limiting** | slowapi, `5/min` on login | Blunts credential brute-force |
| **Real database** | SQLAlchemy async, SQLite → Postgres by URL | Persistence + parameterized queries (no string SQL) |
| **Tests** | 14 pytest cases, isolated in-memory DB | Guards every layer against regressions |
| **Container** | Multi-stage image, runs as non-root | Smaller attack surface, no root in the container |
| **AI endpoint** | Authed, rate-limited, cost-capped Claude bridge | An LLM is a paid, abusable resource — treat it like one |

The application code is database-agnostic: it runs on SQLite locally and on real
**PostgreSQL** in Docker **without a single code change** — only `DATABASE_URL` differs.

---

## Endpoints

| Method | Path | Auth | Notes |
|-------:|------|:----:|-------|
| `GET` | `/health` | — | Liveness/readiness probe |
| `POST` | `/auth/register` | 🔑 code | Create a user (bcrypt-hashed) · requires an owner-issued invite code |
| `POST` | `/auth/login` | — | Returns a JWT · rate-limited `5/min` |
| `GET` | `/items` | — | List items (public read) |
| `POST` | `/items` | ✅ | Create an item |
| `DELETE` | `/items/{id}` | ✅ | Delete an item |
| `POST` | `/ai/summarize` | ✅ | Summarize text via Claude · rate-limited `10/min` · input capped |

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

### Tests

```bash
.venv\Scripts\pytest      # 14 passed
```

---

## Configuration

Copy `.env.example` to `.env` and fill in real values (never commit `.env`):

```env
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(48))">
DATABASE_URL=sqlite+aiosqlite:///./app.db
# Comma-separated invite codes — issue one per user; empty = sign-ups closed.
REGISTRATION_CODE=CODE-ONE,CODE-TWO,CODE-THREE
ANTHROPIC_API_KEY=<your Anthropic key — enables /ai/summarize, else it returns 503>
```

Sign-up is **invite-only and fail-closed**: `/auth/register` accepts only the codes
you list in `REGISTRATION_CODE`, so no one can self-serve an account and run up your
AI bill. With no codes set, registration is disabled entirely.

Secrets are read from the environment only — nothing sensitive is hardcoded, and
`.env` is git-ignored.

---

## Project layout

```
app/
  main.py         # app wiring: lifespan (DB init), rate limiter, routers
  config.py       # env-driven settings (pydantic-settings)
  database.py     # async engine, session, get_db dependency
  models.py       # SQLAlchemy ORM tables (User, Item)
  schemas.py      # Pydantic request/response models
  auth.py         # bcrypt hashing, JWT, get_current_user
  limits.py       # slowapi rate limiter
  routers/        # auth, items, ai
tests/            # pytest suite (isolated in-memory DB)
Dockerfile        # multi-stage, non-root
docker-compose.yml# api + postgres
```
