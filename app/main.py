"""Secure API — FastAPI app wiring: DB lifespan, rate limiter, security headers, routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import DEFAULT_SECRET, settings
from app.database import init_db
from app.limits import limiter
from app.routers import admin, ai, auth, items

_IS_PROD = settings.environment == "production"

# Security response headers (closes the "missing CSP/HSTS/..." findings my own
# scanner, raidkit, reported against this API). CSP still permits the Swagger CDN
# so /docs works in dev; docs are disabled entirely in production (below).
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "frame-ancestors 'none'; base-uri 'self'"
    ),
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


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


app = FastAPI(
    title=settings.app_name,
    version="0.11.0",
    lifespan=lifespan,
    # Don't expose the interactive docs / OpenAPI schema in production.
    docs_url=None if _IS_PROD else "/docs",
    redoc_url=None if _IS_PROD else "/redoc",
    openapi_url=None if _IS_PROD else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response


app.include_router(auth.router)
app.include_router(items.router)
app.include_router(ai.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": app.version}
