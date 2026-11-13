"""Typed application configuration loaded from environment variables / .env files."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    redis_url: str = "redis://localhost:6380/0"

    jwt_secret: SecretStr
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])

    live_trading_enabled: bool = False

    upstox_api_key: SecretStr | None = None
    upstox_api_secret: SecretStr | None = None
    upstox_redirect_uri: str | None = None
    upstox_api_base: str = "https://api.upstox.com"
    # Documented standard-API limits are 50/s, 500/min, 2000/30min. We run at 80% of each.
    upstox_rate_limits: list[tuple[int, float]] = Field(
        default_factory=lambda: [(40, 1.0), (400, 60.0), (1600, 1800.0)]
    )
    token_encryption_key: SecretStr | None = None
    frontend_url: str = "http://localhost:5173"

    data_dir: Path = REPO_DIR / "data"
    artifacts_dir: Path = REPO_DIR / "artifacts"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("upstox_api_key", "upstox_api_secret", "token_encryption_key", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if v == "" else v

    @model_validator(mode="after")
    def _check_safety(self) -> "Settings":
        if len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        if self.live_trading_enabled:
            # Live execution is gated behind Phase 14 compliance work; refuse to boot with it on.
            raise ValueError("LIVE_TRADING_ENABLED=true is not permitted in this build")
        return self

    def database_url(self, db_name: str | None = None) -> str:
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pw}@{self.postgres_host}:"
            f"{self.postgres_port}/{db_name or self.postgres_db}"
        )

    @property
    def upstox_configured(self) -> bool:
        return bool(self.upstox_api_key and self.upstox_api_secret and self.upstox_redirect_uri)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
