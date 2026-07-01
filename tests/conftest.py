"""Test harness: an isolated in-memory DB per test, no touching the real app.db.

We swap the app's get_db dependency for one bound to an in-memory SQLite engine,
build fresh tables before every test, and disable the rate limiter by default so
functional tests don't trip over each other. The rate-limit test re-enables it.
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (register tables on Base)
from app.database import Base, get_db
from app.limits import limiter
from app.main import app

# One shared in-memory DB for the session; StaticPool keeps it alive across
# connections (a plain :memory: engine would forget tables between them).
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    limiter.enabled = False
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def make_token(client, username="not", password="supersecret1"):
    """Register a user and return a valid Bearer token for authed requests."""
    await client.post("/auth/register", json={"username": username, "password": password})
    r = await client.post("/auth/login", data={"username": username, "password": password})
    return r.json()["access_token"]
