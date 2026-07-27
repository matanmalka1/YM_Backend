import importlib
import os

import pytest
from pydantic import ValidationError

from app.config import Settings

_REMOTE_DB = "postgresql+psycopg2://user:pass@remotehost:5432/db"


# ── JWT_SECRET ────────────────────────────────────────────────────────────────


def test_missing_jwt_secret_raises():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(APP_ENV="development", JWT_SECRET="")


# ── staging/production CORS requirement ───────────────────────────────────────


@pytest.mark.parametrize("env", ["staging", "production"])
def test_prod_staging_without_cors_raises(env):
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings(
            APP_ENV=env,
            JWT_SECRET="secret",
            DATABASE_URL=_REMOTE_DB,
            CORS_ALLOWED_ORIGINS="",
            LOG_FORMAT="json",
        )


@pytest.mark.parametrize("env", ["staging", "production"])
def test_prod_staging_with_cors_ok(env):
    s = Settings(
        APP_ENV=env,
        JWT_SECRET="secret",
        DATABASE_URL=_REMOTE_DB,
        CORS_ALLOWED_ORIGINS="https://example.com",
        LOG_FORMAT="json",
    )
    assert s.CORS_ALLOWED_ORIGINS == ["https://example.com"]


# ── localhost DATABASE_URL in prod/staging ────────────────────────────────────


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize(
    "db_url",
    [
        "postgresql+psycopg2://user:pass@localhost:5432/db",
        "postgresql+psycopg2://user:pass@127.0.0.1:5432/db",
    ],
)
def test_prod_staging_localhost_db_raises(env, db_url):
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV=env,
            JWT_SECRET="secret",
            DATABASE_URL=db_url,
            CORS_ALLOWED_ORIGINS="https://example.com",
            LOG_FORMAT="json",
        )


# ── LOG_FORMAT defaults ───────────────────────────────────────────────────────


@pytest.mark.parametrize("env", ["staging", "production"])
def test_log_format_default_json_in_prod(env, monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    s = Settings(
        APP_ENV=env,
        JWT_SECRET="secret",
        DATABASE_URL=_REMOTE_DB,
        CORS_ALLOWED_ORIGINS="https://example.com",
    )
    assert s.LOG_FORMAT == "json"


@pytest.mark.parametrize("env", ["development", "test"])
def test_log_format_default_text_in_dev(env, monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    s = Settings(APP_ENV=env, JWT_SECRET="secret")
    assert s.LOG_FORMAT == "text"


def test_log_format_must_be_json_in_staging_raises():
    with pytest.raises(ValidationError, match="LOG_FORMAT"):
        Settings(
            APP_ENV="staging",
            JWT_SECRET="secret",
            DATABASE_URL=_REMOTE_DB,
            CORS_ALLOWED_ORIGINS="https://example.com",
            LOG_FORMAT="text",
        )


# ── APP_ENV=local normalizes to development ───────────────────────────────────


def test_local_normalizes_to_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    import app.config as config_mod

    config_mod._load_env_files()
    assert os.environ["APP_ENV"] == "development"
    monkeypatch.setenv("APP_ENV", "test")  # restore


# ── ENV_FILE respected ────────────────────────────────────────────────────────


def test_load_env_files_uses_env_file_when_provided(monkeypatch, tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text("SOME_VAR=hello\n")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    captured: dict = {}

    import app.config as config_mod

    original = config_mod.load_dotenv

    def _fake(*, dotenv_path, override):
        captured["dotenv_path"] = str(dotenv_path)
        captured["override"] = override

    config_mod.load_dotenv = _fake
    try:
        config_mod._load_env_files()
    finally:
        config_mod.load_dotenv = original

    assert captured.get("dotenv_path") == str(env_file)
    assert captured.get("override") is False


# ── CORS_ALLOWED_ORIGINS parsing ──────────────────────────────────────────────


def test_cors_origins_parsed_from_comma_string():
    s = Settings(
        APP_ENV="development",
        JWT_SECRET="secret",
        CORS_ALLOWED_ORIGINS="https://a.com, https://b.com , https://c.com",
    )
    assert s.CORS_ALLOWED_ORIGINS == ["https://a.com", "https://b.com", "https://c.com"]


def test_cors_origins_empty_entries_stripped():
    s = Settings(
        APP_ENV="development",
        JWT_SECRET="secret",
        CORS_ALLOWED_ORIGINS="https://a.com,,  ,https://b.com",
    )
    assert s.CORS_ALLOWED_ORIGINS == ["https://a.com", "https://b.com"]


# ── DATABASE_URL defaults ─────────────────────────────────────────────────────


def test_test_env_defaults_to_postgres(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import app.config as config_mod

    importlib.reload(config_mod)
    s = config_mod.Settings(APP_ENV="test", JWT_SECRET="secret")
    assert s.DATABASE_URL.startswith("postgresql+psycopg2://")


def test_sentry_environment_defaults_to_app_env(monkeypatch):
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)

    s = Settings(APP_ENV="development", JWT_SECRET="secret")

    assert s.SENTRY_ENVIRONMENT == "development"


def test_sentry_enabled_requires_dsn_in_production():
    with pytest.raises(ValidationError, match="SENTRY_DSN"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="secret",
            DATABASE_URL=_REMOTE_DB,
            CORS_ALLOWED_ORIGINS="https://example.com",
            LOG_FORMAT="json",
            SENTRY_ENABLED=True,
            SENTRY_DSN="",
        )


def test_login_rate_limit_is_relaxed_in_test_env(monkeypatch):
    monkeypatch.delenv("AUTH_LOGIN_RATE_LIMIT", raising=False)

    s = Settings(APP_ENV="test", JWT_SECRET="secret")

    assert s.AUTH_LOGIN_RATE_LIMIT == "10000/minute"
