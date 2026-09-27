"""
RoomIQ configuration.

All secrets and environment-specific values are read from the environment
(or a local .env file, loaded via python-dotenv) rather than hard-coded.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # -- App --
    APP_NAME: str = "RoomIQ"
    ENV: str = os.getenv("ENV", "development")

    # -- Database --
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/roomiq.db")

    # -- Auth --
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-only-insecure-key-change-me")
    SESSION_MINUTES: int = int(os.getenv("SESSION_MINUTES", "480"))

    # -- Gemini 2.5 --
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or None
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # -- Seeding --
    RESEED: bool = os.getenv("RESEED", "0") == "1"

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
