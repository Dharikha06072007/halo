from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL: str = "gemini-2.5-flash"
    HF_TOKEN: str = Field(default="")
    HF_MODEL: str = "BAAI/bge-base-en-v1.5"
    MONGODB_URI: str = Field(default="")
    MONGODB_DB: str = "skillsync_ai"
    JWT_SECRET: str = Field(default="")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    FRONTEND_URL: str = "http://localhost:5173"
    DEMO_MODE: bool = False

    model_config = SettingsConfigDict(
        env_file=[
            str(Path(__file__).resolve().parents[2] / ".env"),
            str(Path(__file__).resolve().parents[2] / "backend" / ".env"),
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_configured(self) -> bool:
        return bool(
            self.GEMINI_API_KEY and self.HF_TOKEN and self.MONGODB_URI and self.JWT_SECRET
        )


settings = Settings()


def require_required_settings() -> None:
    missing = []
    for name in [
        "GEMINI_API_KEY",
        "HF_TOKEN",
        "MONGODB_URI",
        "JWT_SECRET",
    ]:
        value = getattr(settings, name, "")
        if not value:
            missing.append(name)

    if missing:
        raise RuntimeError("Missing required environment configuration: " + ", ".join(missing))
