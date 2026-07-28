#!/usr/bin/env python3
"""Reset the local dev database to a clean state.

Steps:
  1. Drop and recreate the public schema (wipes all data + alembic history)
  2. Delete all migration files in alembic/versions/
  3. Autogenerate a single fresh migration from current models
  4. Run alembic upgrade head
  5. Run alembic check (fails if models diverge from schema)
  6. Seed fake data

⚠️  WARNING: If you have already deployed migrations to production, squashing
    them here will break the next production deploy. After running this script
    you MUST also reset the production database manually before deploying.

Usage:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py --yes
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py --yes --preserve-users
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py --yes --clients 20
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
VERSIONS_DIR = ROOT_DIR / "alembic" / "versions"
VENV_PYTHON = ROOT_DIR / ".venv" / "bin" / "python"
VENV_ALEMBIC = ROOT_DIR / ".venv" / "bin" / "alembic"

# Matches every enum type name declared in the migration, e.g.
# sa.Enum('open', 'done', name='taskstatus') -> taskstatus
ENUM_NAME_PATTERN = re.compile(r"(?:sa\.Enum|postgresql\.ENUM)\([^)]*name=[\"'](\w+)[\"']")

ENV = {
    **os.environ,
    "APP_ENV": "development",
    "ENV_FILE": str(ROOT_DIR / ".env.development"),
    "JWT_SECRET": os.environ.get("JWT_SECRET", "dev-seed-secret"),
}


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, env=ENV, cwd=ROOT_DIR, text=True)


def _read_db_url() -> str:
    env_file = ROOT_DIR / ".env.development"
    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip()
            # psycopg2 driver prefix → plain postgresql for psql
            return re.sub(r"^postgresql\+\w+://", "postgresql://", url)
    raise SystemExit("DATABASE_URL not found in .env.development")


def _confirm() -> None:
    print()
    print("=" * 60)
    print("  RESET DEV DATABASE")
    print("=" * 60)
    print()
    print("  This will:")
    print("    1. DROP + recreate the public schema (all data gone)")
    print("    2. Delete all files in alembic/versions/")
    print("    3. Autogenerate a single fresh migration")
    print("    4. Run alembic upgrade head + alembic check")
    print("    5. Seed fake data")
    print()
    print("  ⚠️  If production has existing migrations, you MUST also")
    print("      reset production manually before the next deploy.")
    print()
    answer = input("  Continue? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)
    print()


DROP_SCHEMA_SQL = "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
COMPOSE_DB_SERVICE = "db"


def _psql_command(db_url: str) -> list[str]:
    """Prefer a host psql; fall back to the one inside the Compose db service.

    The database only has to exist for the developer running this — it does not
    have to be installed on their machine. Requiring a host psql made this script
    unusable on a Docker-only setup, which is the documented way to run the dev DB.
    """
    if shutil.which("psql"):
        return ["psql", db_url, "-c", DROP_SCHEMA_SQL]
    if not shutil.which("docker"):
        raise SystemExit(
            "Neither psql nor docker is on PATH — cannot reach the dev database. "
            "Install libpq (brew install libpq) or start Docker."
        )
    print("       psql not on PATH — using the Compose db service instead")
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        COMPOSE_DB_SERVICE,
        "psql",
        db_url,
        "-c",
        DROP_SCHEMA_SQL,
    ]


def _drop_schema(db_url: str) -> None:
    print("[1/5] Dropping and recreating public schema...")
    _run(_psql_command(db_url))


def _delete_migrations() -> None:
    print("[2/5] Deleting migration files...")
    deleted = 0
    for f in VERSIONS_DIR.glob("*.py"):
        if f.name == "__init__.py":
            continue
        f.unlink()
        print(f"       deleted {f.name}")
        deleted += 1
    if deleted == 0:
        print("       (no migration files found)")


def inject_enum_drops(content: str) -> tuple[str, int]:
    """Append `DROP TYPE` for every enum type created by upgrade().

    Alembic creates a standalone Postgres enum TYPE per inline `sa.Enum` column,
    but `op.drop_table` does not remove it, so a downgrade -> upgrade roundtrip
    (what CI runs) fails with `type "..." already exists`.

    Appends to the end of the file, which is the tail of `downgrade()` in the
    alembic template — the statements must run after every `drop_table`.
    """
    if "DROP TYPE IF EXISTS" in content:
        return content, 0

    upgrade_src, _, _ = content.partition("def downgrade() -> None:")
    names = sorted(set(ENUM_NAME_PATTERN.findall(upgrade_src)))
    if not names:
        return content, 0

    block = [
        "",
        "    # Enum types created implicitly by sa.Enum in create_table. Postgres keeps",
        "    # them as standalone objects that drop_table does not remove, so a",
        "    # downgrade -> upgrade roundtrip would fail without this.",
        '    op.execute("DROP SEQUENCE IF EXISTS client_office_number_seq")',
        *[f'    op.execute("DROP TYPE IF EXISTS {name}")' for name in names],
    ]
    return content.rstrip("\n") + "\n" + "\n".join(block) + "\n", len(names)


def _autogenerate_migration() -> None:
    print("[3/5] Autogenerating fresh migration...")
    _run(
        [
            str(VENV_ALEMBIC),
            "revision",
            "--autogenerate",
            "-m",
            "initial",
        ]
    )

    # autogenerate cannot detect bare sequences — inject it manually
    migration_files = sorted(VERSIONS_DIR.glob("*.py"))
    migration_files = [f for f in migration_files if f.name != "__init__.py"]
    if not migration_files:
        raise SystemExit("Migration file not found after autogenerate")
    migration_file = migration_files[-1]
    original = migration_file.read_text()
    content = original
    sequence_line = (
        '    op.execute("CREATE SEQUENCE IF NOT EXISTS client_office_number_seq START 100001")\n'
    )
    marker = "def upgrade() -> None:\n"
    if sequence_line not in content:
        # insert after the opening of upgrade(), before the first op. call
        insert_after = marker + '    """Upgrade schema."""\n'
        if insert_after in content:
            content = content.replace(insert_after, insert_after + sequence_line)
        else:
            content = content.replace(marker, marker + sequence_line)
        print(f"       injected sequence into {migration_file.name}")

    # autogenerate never drops the enum types it implicitly creates
    content, enum_count = inject_enum_drops(content)
    if enum_count:
        print(f"       injected {enum_count} enum type drops into {migration_file.name}")

    if content != original:
        migration_file.write_text(content)


def _upgrade_and_check() -> None:
    print("[4/5] Running alembic upgrade head...")
    _run([str(VENV_ALEMBIC), "upgrade", "head"])

    print("[5/5] Running alembic check (model/schema drift)...")
    result = _run([str(VENV_ALEMBIC), "check"], check=False)
    if result.returncode != 0:
        print()
        print("  ✗ alembic check failed — models and schema are out of sync.")
        print("    Review the autogenerated migration and fix missing columns/tables.")
        sys.exit(1)
    print("       Models match schema.")


def _seed(*, preserve_users: bool, clients: int) -> None:
    print("[6/6] Seeding fake data...")
    cmd = [str(VENV_PYTHON), "scripts/dev/seed_fake_data.py", "--reset", "--clients", str(clients)]
    if preserve_users:
        cmd.append("--preserve-users")
    _run(cmd)


def main() -> None:
    if os.environ.get("APP_ENV", "development") != "development":
        raise SystemExit("This script only runs in APP_ENV=development")

    parser = argparse.ArgumentParser(description="Reset local dev DB to clean state")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument(
        "--preserve-users", action="store_true", help="Keep existing users after seed"
    )
    parser.add_argument(
        "--clients", type=int, default=60, help="Number of fake clients to seed (default: 60)"
    )
    args = parser.parse_args()

    if not args.yes:
        _confirm()

    db_url = _read_db_url()

    _drop_schema(db_url)
    _delete_migrations()
    _autogenerate_migration()
    _upgrade_and_check()
    _seed(preserve_users=args.preserve_users, clients=args.clients)

    print()
    print("Done. Dev DB is clean and seeded.")


if __name__ == "__main__":
    main()
