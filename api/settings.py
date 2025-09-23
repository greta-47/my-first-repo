from __future__ import annotations

import os

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = os.getenv("ENV", "dev")
    ENFORCE_HTTPS: bool = os.getenv("ENFORCE_HTTPS", "false").lower() == "true"
    CSP_REPORT_ONLY: bool = os.getenv("CSP_REPORT_ONLY", "false").lower() == "true"
    ALLOWED_ORIGINS: list[AnyHttpUrl] | None = None

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v):
        # If provided explicitly, accept list or comma-separated string
        if v:
            if isinstance(v, list):
                return v
            return [o.strip() for o in str(v).split(",") if o.strip()]

        # Default sets depending on environment
        if os.getenv("ENV", "dev") == "dev":
            return [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
            ]
        return ["https://recoveryos.org", "https://www.recoveryos.org"]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
