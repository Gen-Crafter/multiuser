"""Application configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "LinkedInCampaignPlatform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me"
    ALLOWED_HOSTS: str = "*"

    # ── Database ─────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "linkedin_platform"
    POSTGRES_USER: str = "platform_user"
    POSTGRES_PASSWORD: str = "change-me"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Redis ────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    @property
    def REDIS_URL(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Ollama / LLM ────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # ── Google OAuth ────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/api/auth/callback/google"

    # ── Encryption ──────────────────────────────────────
    ENCRYPTION_KEY: str = "change-me"

    # ── Browser Automation ──────────────────────────────
    BROWSER_HEADLESS: bool = True
    BROWSER_POOL_SIZE: int = 50
    SESSION_STORAGE_PATH: str = "/app/sessions"

    # ── Proxy ───────────────────────────────────────────
    PROXY_LIST_PATH: str = "/app/proxies.txt"
    PROXY_ROTATION_ENABLED: bool = True

    # ── Rate limits (defaults for normal accounts) ──────
    DEFAULT_CONNECTIONS_PER_DAY: int = 25
    DEFAULT_MESSAGES_PER_DAY: int = 50
    DEFAULT_PROFILE_VIEWS_PER_DAY: int = 80
    DEFAULT_POSTS_PER_DAY: int = 2
    PREMIUM_CONNECTIONS_PER_DAY: int = 50
    PREMIUM_MESSAGES_PER_DAY: int = 100
    PREMIUM_PROFILE_VIEWS_PER_DAY: int = 150
    PREMIUM_POSTS_PER_DAY: int = 5


@lru_cache()
def get_settings() -> Settings:
    return Settings()
