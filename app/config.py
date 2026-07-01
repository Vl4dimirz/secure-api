"""Central configuration — reads from env / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Secure API"
    secret_key: str = "dev-secret-change-me-in-prod"
    access_token_expire_minutes: int = 30
    # SQLite for local dev; swap to Postgres in prod (postgresql+asyncpg://...).
    database_url: str = "sqlite+aiosqlite:///./app.db"
    # AI bridge — key is read from env/.env, never hardcoded. Empty = AI disabled.
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
