"""Secure API — FastAPI app wiring: DB lifespan, rate limiter, routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import DEFAULT_SECRET, settings
from app.database import init_db
from app.limits import limiter
from app.routers import admin, ai, auth, items


def _check_production_hardening() -> None:
    """Fail-closed on insecure defaults in production, so a careless deploy can't
    ship the public repo's default JWT secret (which would let anyone forge tokens)."""
    if settings.environment == "production" and settings.secret_key == DEFAULT_SECRET:
        raise RuntimeError(
            "Refusing to start: SECRET_KEY is still the public default in production. "
            "Set a strong SECRET_KEY (python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_production_hardening()
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.9.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(ai.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": app.version}
