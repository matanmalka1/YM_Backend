from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context

# Load app config for DATABASE_URL
from app.config import settings as app_settings

from app.database import Base

# Required for Alembic autogenerate to detect all ORM tables.
# Keep the model list centralized in app/model_registry.py.
import app.model_registry  # noqa: F401


alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

alembic_config.set_main_option("sqlalchemy.url", app_settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _widen_alembic_version_if_needed(connectable) -> None:
    """Ensure alembic_version.version_num is VARCHAR(255) on PostgreSQL.

    Alembic's default is VARCHAR(32), which is too short for revision IDs
    of the form 'NNNN_<description>'. This function either widens an existing
    column or pre-creates the table with the correct width so the first
    migration does not overflow it.

    Uses a separate connection so the commit does not interfere with
    Alembic's own migration transaction.
    """
    with connectable.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'alembic_version')"
            )
        ).scalar()
        if exists:
            conn.execute(
                text(
                    "ALTER TABLE alembic_version "
                    "ALTER COLUMN version_num TYPE VARCHAR(255)"
                )
            )
        else:
            conn.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(255) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )
        conn.commit()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    _widen_alembic_version_if_needed(connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
