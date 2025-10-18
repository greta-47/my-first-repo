from __future__ import annotations

import os
from typing import Optional

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="production", description="Environment name")
    app_version: str = Field(default="unknown", description="Application version")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Enable debug mode")

    request_log_redact: bool = Field(default=True, description="Redact PII in request logs")
    deidentify_default: bool = Field(default=True, description="Use display codes by default")

    database_url: SecretStr = Field(
        default=SecretStr("postgresql://user:pass@localhost:5432/recoveryos"),
        description="Primary database connection string",
    )
    database_ro_url: Optional[SecretStr] = Field(default=None, description="Read-only replica URL")
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_overflow: int = Field(default=20, description="Database pool overflow")

    rate_limit_capacity: int = Field(default=5, description="Rate limit bucket capacity")
    rate_limit_window_seconds: int = Field(default=10, description="Rate limit time window")

    enable_otel_tracing: bool = Field(default=False, description="Enable OpenTelemetry tracing")
    otel_exporter_otlp_endpoint: Optional[HttpUrl] = Field(default=None)
    otel_exporter_otlp_headers: Optional[SecretStr] = Field(default=None)
    otel_service_name: str = Field(default="recoveryos-api")
    traces_sample_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    metrics_enabled: bool = Field(default=True)

    risk_model_version: str = Field(default="v0.1.0")
    risk_grace_days: int = Field(default=3, description="Days before risk scoring starts")
    risk_bands: str = Field(default="0-29,30-54,55-74,75-100", description="Risk band thresholds")

    enable_crisis_alerts: bool = Field(default=True)

    sentry_dsn: Optional[SecretStr] = Field(
        default=None, description="Sentry DSN for error tracking"
    )
    log_stacks_to_sentry: bool = Field(default=False, description="Send stack traces to Sentry")

    db_auto_migrate: bool = Field(default=False, description="Run Alembic migrations on startup")
    strict_startup: bool = Field(default=False, description="Fail hard on startup errors")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, validate_default=True
    )

    @classmethod
    def for_environment(cls, env: str = "production") -> "Settings":
        if env == "development":
            return cls(
                app_env="development",
                log_level="DEBUG",
                debug=True,
                traces_sample_rate=1.0,
                database_url=SecretStr("postgresql://user:pass@localhost:5432/recoveryos_dev"),
            )
        elif env == "testing":
            return cls(
                app_env="testing",
                log_level="WARNING",
                database_url=SecretStr(
                    "postgresql://test_user:test_pass@localhost:5432/recoveryos_test"
                ),
                rate_limit_capacity=100,
            )
        return cls()


def get_settings() -> Settings:
    return Settings.for_environment(os.getenv("APP_ENV", "production"))


settings = get_settings()
