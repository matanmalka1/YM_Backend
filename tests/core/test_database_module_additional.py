import importlib

import pytest

import app.config as config_mod
import app.database as database_mod
from app.core.logging_config import (
    begin_request_log_stats,
    clear_request_id,
    clear_request_log_stats,
    get_request_log_stats,
    record_sql_query,
)


def test_get_db_closes_session_on_generator_close(monkeypatch):
    class _DB:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    db = _DB()
    monkeypatch.setattr(database_mod, "SessionLocal", lambda: db)

    dep = database_mod.get_db()
    yielded = next(dep)
    assert yielded is db
    assert db.closed is False

    dep.close()
    assert db.closed is True


def test_get_db_does_not_log_summary_before_status_is_known(monkeypatch):
    class _DB:
        def close(self):
            pass

    calls = []
    monkeypatch.setattr(database_mod, "SessionLocal", _DB)
    monkeypatch.setattr(
        database_mod,
        "log_request_summary",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    begin_request_log_stats()
    record_sql_query("SELECT 1", 1.0)

    try:
        dep = database_mod.get_db()
        next(dep)
        dep.close()

        assert calls == []
        assert get_request_log_stats() is not None
    finally:
        clear_request_log_stats()
        clear_request_id()


def test_database_module_rejects_sqlite_in_production(monkeypatch):
    class _Cfg:
        APP_ENV = "production"
        DATABASE_URL = "sqlite:///should_fail.db"

    original = config_mod.settings
    monkeypatch.setattr(config_mod, "settings", _Cfg)
    try:
        with pytest.raises(RuntimeError):
            importlib.reload(database_mod)
    finally:
        config_mod.settings = original
        importlib.reload(database_mod)
