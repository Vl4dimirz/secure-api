"""Async database layer (SQLAlchemy 2.0). SQLite locally, Postgres in prod via URL."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from sqlalchemy import select

    from app import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed invite codes from config into the table (idempotent — never resets the
    # 'used' state of a code that's already been consumed).
    async with SessionLocal() as session:
        for code in settings.valid_codes():
            found = await session.execute(
                select(models.InviteCode).where(models.InviteCode.code == code)
            )
            if found.scalar_one_or_none() is None:
                session.add(models.InviteCode(code=code))
        await session.commit()
