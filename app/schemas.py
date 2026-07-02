"""Pydantic v2 schemas — request validation + response shaping (reads ORM objects)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class Item(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    # bcrypt only hashes the first 72 bytes — cap here so a longer password isn't
    # silently truncated (which would make chars past 72 meaningless).
    password: str = Field(min_length=8, max_length=72)
    # Invite code the API owner issues. Without a valid one, no account is created,
    # so nobody can reach the paid AI endpoint and burn tokens.
    code: str = Field(min_length=1, max_length=64, description="Registration invite code")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SummarizeRequest(BaseModel):
    # max_length caps token spend per call — an input-size guard, not just UX.
    text: str = Field(min_length=1, max_length=6000)


class SummarizeResponse(BaseModel):
    summary: str
    calls_remaining: int  # trial calls left on this account after this one


class GenerateCodesRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=100)
    prefix: str = Field(default="INK", min_length=1, max_length=12)


class GeneratedCodes(BaseModel):
    created: list[str]


class InviteCodeStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    used_at: datetime | None
    used_by: str | None
