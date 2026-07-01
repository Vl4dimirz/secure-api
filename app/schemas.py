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
    password: str = Field(min_length=8, max_length=128)
    # Invite code the API owner issues. Without a valid one, no account is created,
    # so nobody can reach the paid AI endpoint and burn tokens.
    code: str = Field(min_length=1, description="Registration invite code")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SummarizeRequest(BaseModel):
    # max_length caps token spend per call — an input-size guard, not just UX.
    text: str = Field(min_length=1, max_length=6000)


class SummarizeResponse(BaseModel):
    summary: str
    calls_remaining: int  # trial calls left on this account after this one
