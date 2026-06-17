"""Central configuration. Secrets only via env — never hardcoded, never logged (§3.3)."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Core
    database_url: str = "postgresql+asyncpg://parallax:parallax@localhost:5435/parallax"
    redis_url: str = "redis://localhost:6380/0"
    environment: str = "local"
    log_level: str = "INFO"

    # Run mode
    data_mode: Literal["SEED", "LIVE"] = "SEED"

    # AI / synthesis
    inference_provider: Literal["anthropic", "openai", "template"] = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model_cheap: str = "claude-haiku-4-5-20251001"
    anthropic_model_premium: str = "claude-opus-4-8"
    openai_api_key: str = ""

    # Adapters
    companies_house_api_key: str = ""
    geocoder_provider: str = "postcodes_io"
    ideal_postcodes_api_key: str = ""
    postcoder_api_key: str = ""
    epc_auth_token: str = ""  # pre-encoded base64(email:apikey), if you have it
    epc_email: str = ""        # EPC registration email (paired with the key below / token above)
    epc_api_key: str = ""      # EPC API key (alternative to putting it in epc_auth_token)
    hmlr_api_key: str = ""

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    access_token_ttl_min: int = 10080

    @field_validator("database_url", mode="before")
    @classmethod
    def _ensure_async_driver(cls, v: str) -> str:
        """Managed providers (Railway, Heroku, etc.) emit ``postgres(ql)://``; the async engine
        needs the asyncpg driver. Normalise so the same value works everywhere."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    @property
    def sync_database_url(self) -> str:
        """psycopg/alembic-friendly sync URL derived from the async one."""
        return self.database_url.replace("+asyncpg", "+psycopg2").replace(
            "postgresql+psycopg2", "postgresql"
        )

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
