#!/usr/bin/env python3
"""Print the actual database schema via SQLAlchemy inspect().

Shows tables, columns (type, nullable), indexes (unique, partial), foreign keys,
and check constraints — all from the live DB, not the ORM models.

Usage:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/dump_schema.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/dump_schema.py --table client_records
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/dump_schema.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "dev-seed-secret")


def _load_env() -> None:
    env_file = ROOT_DIR / ".env.development"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _inspect(table_filter: str | None) -> list[dict]:
    from sqlalchemy import create_engine, inspect

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise SystemExit("DATABASE_URL not set")

    engine = create_engine(db_url)
    insp = inspect(engine)

    table_names = sorted(insp.get_table_names(schema="public"))
    if table_filter:
        table_names = [t for t in table_names if table_filter.lower() in t.lower()]
        if not table_names:
            raise SystemExit(f"No tables matching {table_filter!r}")

    result = []
    for table in table_names:
        entry: dict = {
            "table": table,
            "columns": [],
            "indexes": [],
            "foreign_keys": [],
            "check_constraints": [],
        }

        for col in insp.get_columns(table, schema="public"):
            entry["columns"].append(
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col["nullable"],
                    "default": str(col.get("default") or ""),
                }
            )

        for idx in insp.get_indexes(table, schema="public"):
            entry["indexes"].append(
                {
                    "name": idx["name"],
                    "columns": idx["column_names"],
                    "unique": idx["unique"],
                    "dialect_options": {
                        k: v for k, v in (idx.get("dialect_options") or {}).items()
                    },
                }
            )

        for fk in insp.get_foreign_keys(table, schema="public"):
            entry["foreign_keys"].append(
                {
                    "columns": fk["constrained_columns"],
                    "references": f"{fk['referred_table']}.{fk['referred_columns']}",
                }
            )

        pk = insp.get_pk_constraint(table, schema="public")
        entry["primary_key"] = pk.get("constrained_columns", [])

        uq = insp.get_unique_constraints(table, schema="public")
        entry["unique_constraints"] = [
            {"name": u["name"], "columns": u["column_names"]} for u in uq
        ]

        try:
            cc = insp.get_check_constraints(table, schema="public")
            entry["check_constraints"] = [{"name": c["name"], "sqltext": c["sqltext"]} for c in cc]
        except Exception:
            pass

        result.append(entry)

    return result


def _print_text(data: list[dict]) -> None:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    CYAN = "\033[36m"

    for entry in data:
        print(f"\n{BOLD}{entry['table']}{RESET}")

        if entry.get("primary_key"):
            print(f"  {DIM}PK:{RESET} {', '.join(entry['primary_key'])}")

        print(f"  {DIM}Columns:{RESET}")
        for col in entry["columns"]:
            null_str = "" if col["nullable"] else f" {DIM}NOT NULL{RESET}"
            default_str = f" {DIM}default={col['default']}{RESET}" if col["default"] else ""
            print(f"    {col['name']:<35} {CYAN}{col['type']}{RESET}{null_str}{default_str}")

        if entry.get("indexes"):
            print(f"  {DIM}Indexes:{RESET}")
            for idx in entry["indexes"]:
                uq = " UNIQUE" if idx["unique"] else ""
                cols = ", ".join(c or "?" for c in idx["columns"])
                partial = idx["dialect_options"].get("postgresql_where", "")
                partial_str = f" WHERE {partial}" if partial else ""
                print(f"    {idx['name']:<45} ({cols}){uq}{partial_str}")

        if entry.get("foreign_keys"):
            print(f"  {DIM}FKs:{RESET}")
            for fk in entry["foreign_keys"]:
                print(f"    {', '.join(fk['columns'])} → {fk['references']}")

        if entry.get("unique_constraints"):
            print(f"  {DIM}Unique constraints:{RESET}")
            for u in entry["unique_constraints"]:
                print(f"    {u['name']}: ({', '.join(u['columns'])})")

        if entry.get("check_constraints"):
            print(f"  {DIM}Check constraints:{RESET}")
            for c in entry["check_constraints"]:
                print(f"    {c['name']}: {c['sqltext']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump actual DB schema via SQLAlchemy inspect()")
    parser.add_argument("--table", help="Filter by table name (substring match)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    _load_env()
    data = _inspect(args.table)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Schema dump — {len(data)} table(s)")
        _print_text(data)


if __name__ == "__main__":
    main()
