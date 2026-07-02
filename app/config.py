"""Central configuration — reads from env / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict

# The insecure dev default. It lives in the public repo, so any deploy that
# forgets to override SECRET_KEY could have its JWTs forged — startup refuses
# to boot in production while this is still the value (see main.py lifespan).
DEFAULT_SECRET = "dev-secret-change-me-in-prod"


class Settings(BaseSettings):
    app_name: str = "Secure API"
    # dev | production. In production the app refuses insecure defaults.
    environment: str = "dev"
    secret_key: str = DEFAULT_SECRET
    access_token_expire_minutes: int = 30
    # SQLite for local dev; swap to Postgres in prod (postgresql+asyncpg://...).
    database_url: str = "sqlite+aiosqlite:///./app.db"
    # Optional shared store for rate limits (e.g. redis://host:6379). Empty =
    # in-memory (single instance only).
    redis_url: str = ""
    # AI bridge — key is read from env/.env, never hardcoded. Empty = AI disabled.
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"
    # Per-account AI call budget (trial). After this many calls the user is cut off
    # so a shared/leaked account can't run the bill up forever.
    ai_call_quota: int = 10
    # Admin token guarding /admin/* (issuing/revoking invite codes). Empty = the
    # admin API is DISABLED (fail-closed) — no one can mint codes without it.
    admin_token: str = ""
    # Invite codes the owner issues to allow sign-ups — a COMMA-SEPARATED list.
    # These are SEEDED into the invite_codes table on startup; each one is then
    # SINGLE-USE (consumed on registration). Empty = registration is CLOSED
    # (fail-closed): a fresh deploy can't be self-served into abusing the paid AI.
    registration_code: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def valid_codes(self) -> set[str]:
        """The set of accepted invite codes (blank entries dropped)."""
        return {c.strip() for c in self.registration_code.split(",") if c.strip()}


settings = Settings()
