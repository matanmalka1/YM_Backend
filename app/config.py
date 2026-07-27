from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

_DEFAULT_CORS = (
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
)


def _load_env_files() -> None:
    if load_dotenv is None:
        return

    root_dir = Path(__file__).resolve().parents[1]

    raw_app_env = (os.getenv("APP_ENV") or "development").strip().lower()
    app_env = "development" if raw_app_env == "local" else raw_app_env
    os.environ["APP_ENV"] = app_env

    env_file = os.getenv("ENV_FILE")
    if env_file:
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        selected = root_dir / f".env.{app_env}"
        if selected.exists():
            load_dotenv(dotenv_path=selected, override=False)


_load_env_files()

_DEFAULT_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/binder_crm"


def _split_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_ignore_empty=False,
        extra="ignore",
        populate_by_name=True,
    )

    APP_ENV: Literal["development", "test", "staging", "production"] = "development"
    PORT: int = 8000

    DATABASE_URL: str = _DEFAULT_DATABASE_URL

    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    AUTH_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 5
    PASSWORD_RESET_DEV_LOG: bool = False
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    FRONTEND_PASSWORD_RESET_URL: str = "http://localhost:5173/reset-password"

    # Raw comma-separated string; read list via .CORS_ALLOWED_ORIGINS property.
    # Accepts env var CORS_ALLOWED_ORIGINS or constructor kwarg CORS_ALLOWED_ORIGINS.
    CORS_ALLOWED_ORIGINS_RAW: Annotated[
        str,
        Field(
            default=_DEFAULT_CORS,
            validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS_RAW", "CORS_ALLOWED_ORIGINS"),
        ),
    ] = _DEFAULT_CORS

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["text", "json"] = "text"
    LOG_SQL: bool = False
    LOG_SLOW_REQUEST_MS: int = 500
    LOG_SLOW_QUERY_MS: int = 250
    LOG_HIGH_QUERY_COUNT: int = 20

    AUTH_LOGIN_RATE_LIMIT: str = "5/minute"

    SENTRY_ENABLED: bool = False
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    NOTIFICATIONS_ENABLED: bool = False

    BREVO_API_KEY: str = ""
    BREVO_API_URL: str = "https://api.brevo.com/v3/smtp/email"
    EMAIL_FROM_ADDRESS: str = ""
    EMAIL_FROM_NAME: str = ""

    WHATSAPP_API_KEY: str = ""
    WHATSAPP_API_URL: str = "https://waba.360dialog.io/v1/messages"
    WHATSAPP_FROM_NUMBER: str = ""

    INVOICE_PROVIDER_BASE_URL: str = ""
    INVOICE_PROVIDER_API_KEY: str = ""

    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_ENDPOINT_URL: str = ""
    R2_REGION: str = "auto"
    LOCAL_STORAGE_PATH: str = "./storage"

    @property
    def CORS_ALLOWED_ORIGINS(self) -> list[str]:
        return _split_origins(self.CORS_ALLOWED_ORIGINS_RAW)

    @model_validator(mode="before")
    @classmethod
    def apply_env_defaults(cls, values: dict) -> dict:
        app_env = str(values.get("APP_ENV") or os.getenv("APP_ENV") or "development").lower()

        if "LOG_FORMAT" not in values and os.getenv("LOG_FORMAT") is None:
            values["LOG_FORMAT"] = "json" if app_env in ("staging", "production") else "text"

        if "LOG_SQL" not in values and os.getenv("LOG_SQL") is None:
            values["LOG_SQL"] = app_env == "development"

        if "SENTRY_ENVIRONMENT" not in values and os.getenv("SENTRY_ENVIRONMENT") is None:
            values["SENTRY_ENVIRONMENT"] = app_env

        if "AUTH_LOGIN_RATE_LIMIT" not in values and os.getenv("AUTH_LOGIN_RATE_LIMIT") is None:
            values["AUTH_LOGIN_RATE_LIMIT"] = "10000/minute" if app_env == "test" else "5/minute"

        if "REFRESH_COOKIE_SAMESITE" not in values and os.getenv("REFRESH_COOKIE_SAMESITE") is None:
            values["REFRESH_COOKIE_SAMESITE"] = "none" if app_env == "production" else "lax"

        return values

    @model_validator(mode="after")
    def validate_config(self) -> Settings:
        if not self.JWT_SECRET:
            raise ValueError("JWT_SECRET חייב להיות מוגדר")

        if self.APP_ENV in ("staging", "production"):
            if not self.CORS_ALLOWED_ORIGINS:
                raise ValueError("CORS_ALLOWED_ORIGINS חייב להיות מוגדר")

            db = self.DATABASE_URL.lower()
            if "localhost" in db or "127.0.0.1" in db:
                raise ValueError(
                    f"DATABASE_URL מצביע על localhost ב-{self.APP_ENV} — חובה להגדיר DB מרוחק"
                )

            if self.LOG_FORMAT != "json":
                raise ValueError(f"LOG_FORMAT חייב להיות json ב-{self.APP_ENV}")

            if self.SENTRY_ENABLED and not self.SENTRY_DSN:
                raise ValueError(
                    f"SENTRY_DSN חייב להיות מוגדר כאשר SENTRY_ENABLED=true ב-{self.APP_ENV}"
                )

        return self


settings = Settings()
