"""Async database layer (SQLAlchemy 2.0). SQLite locally, Postgres in prod via URL."""
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Project root = parent of the app/ package. Used to locate the Alembic scripts.
BASE_DIR = Path(__file__).resolve().parent.parent

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def _upgrade_to_head() -> None:
    """Run Alembic migrations up to the latest revision.

    Alembic drives its own event loop internally, so we run it in a worker thread
    to avoid clashing with the app's running loop. We build the Config in code (no
    .ini file) so it never hijacks the app's logging setup.
    """
    from alembic import command
    from alembic.config import Config

    def _run() -> None:
        cfg = Config()
        cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
        command.upgrade(cfg, "head")

    await asyncio.to_thread(_run)


async def init_db() -> None:
    from sqlalchemy import select

    from app import models

    # Alembic owns the schema now: migrate to head instead of create_all, so a
    # schema change is a new migration — never a database wipe.
    await _upgrade_to_head()

    # Seed invite codes from config (idempotent — never resets a consumed code).
    async with SessionLocal() as session:
        for code in settings.valid_codes():
            found = await session.execute(
                select(models.InviteCode).where(models.InviteCode.code == code)
            )
            if found.scalar_one_or_none() is None:
                session.add(models.InviteCode(code=code))
        await session.commit()
