"""Phase 1 — PostgreSQL migration round-trip + fail-safe downgrade.

Migrations 1a/1b are PostgreSQL-specific (JSONB ``USING`` casts), so this test is
opt-in: it runs only when ``AUDIT_PG_MAINT_URL`` points at a reachable PostgreSQL
maintenance database (e.g.
``postgresql+psycopg2://postgres:postgres@localhost:5432/postgres``). It creates a
throwaway database, runs upgrade head, proves the fail-safe downgrade refuses when a
NULL-actor (system) row exists, and tears the database down.

Locally:
    AUDIT_PG_MAINT_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres \
        APP_ENV=test JWT_SECRET=x .venv/bin/python -m pytest \
        tests/audit/test_phase1_migration_roundtrip.py
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

_MAINT_URL = os.getenv("AUDIT_PG_MAINT_URL")

pytestmark = pytest.mark.skipif(
    not _MAINT_URL,
    reason="AUDIT_PG_MAINT_URL not set — PostgreSQL-only migration round-trip is opt-in",
)


def _alembic_config(db_url: str):
    from alembic.config import Config

    cfg = Config(os.path.join(os.getcwd(), "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_phase1_roundtrip_and_failsafe_downgrade():
    from alembic import command
    from app import config

    db_name = f"audit_p1_{uuid.uuid4().hex[:10]}"
    maint = create_engine(_MAINT_URL, isolation_level="AUTOCOMMIT")
    with maint.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    db_url = _MAINT_URL.rsplit("/", 1)[0] + f"/{db_name}"
    # alembic/env.py forces sqlalchemy.url = app config DATABASE_URL, so point the
    # app config at the throwaway PostgreSQL DB for the duration of the round-trip.
    original_db_url = config.settings.DATABASE_URL
    config.settings.DATABASE_URL = db_url
    try:
        cfg = _alembic_config(db_url)
        command.upgrade(cfg, "head")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            cols = {
                row[0]: row[1]
                for row in conn.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name='entity_audit_logs'"
                    )
                )
            }
            assert cols["old_value"] == "jsonb"
            assert cols["new_value"] == "jsonb"
            assert cols["metadata_json"] == "jsonb"
            assert cols["actor_type"] == "character varying"
            # performed_by is nullable after 1a.
            null_ok = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name='entity_audit_logs' AND column_name='performed_by'"
                )
            ).scalar()
            assert null_ok == "YES"
        engine.dispose()

        # Clean round-trip: with no rows, downgrade fully reverses to the initial
        # schema (old_value back to Text, actor columns gone), then re-upgrades.
        command.downgrade(cfg, "3e2669e69e32")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            cols = {
                row[0]: row[1]
                for row in conn.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name='entity_audit_logs'"
                    )
                )
            }
            assert cols["old_value"] == "text"
            assert cols["new_value"] == "text"
            assert "actor_type" not in cols
            assert "actor_display_name" not in cols
            assert "metadata_json" not in cols
        engine.dispose()
        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            restored = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='entity_audit_logs' AND column_name='old_value'"
                )
            ).scalar()
            assert restored == "jsonb"

        # Insert a NULL-actor (system) row, then prove the downgrade refuses.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO entity_audit_logs "
                    "(entity_type, entity_id, performed_by, actor_type, action, "
                    " new_value, metadata_json, performed_at) "
                    "VALUES ('signature_request', 1, NULL, 'system', "
                    "'signature_request.expired', '{\"status\":\"expired\"}'::jsonb, "
                    '\'{"client_record_id":"1"}\'::jsonb, now())'
                )
            )
        engine.dispose()

        with pytest.raises(Exception) as exc_info:
            command.downgrade(cfg, "3e2669e69e32")
        assert "performed_by" in str(exc_info.value)

        # Fail-safe is atomic: the NULL row survives and JSONB stays in place.
        engine = create_engine(db_url)
        with engine.connect() as conn:
            remaining = conn.execute(
                text("SELECT count(*) FROM entity_audit_logs WHERE performed_by IS NULL")
            ).scalar()
            assert remaining == 1
            still_jsonb = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='entity_audit_logs' AND column_name='old_value'"
                )
            ).scalar()
            assert still_jsonb == "jsonb"
        engine.dispose()
    finally:
        config.settings.DATABASE_URL = original_db_url
        with maint.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname='{db_name}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        maint.dispose()
