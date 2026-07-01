"""Secure API — FastAPI app wiring: DB lifespan, rate limiter, routers."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import init_db
from app.limits import limiter
from app.routers import ai, auth, items


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.5.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(items.router)
app.include_router(ai.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": app.version}
