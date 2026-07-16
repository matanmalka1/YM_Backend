## Scope
This file owns only:
- Backend script usage notes and local tooling reference.

This file must not contain:
- Canonical workflow rules.
- Product/domain behavior.
- Architecture decisions.

Source of truth: reference

# scripts/

Utility scripts for local development, data seeding, auditing, and tooling.

Run all scripts from the **backend repository root** using the virtualenv Python.

---

## Quick Start — Main CLI

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py
```

Useful direct commands:

```bash
# list everything registered in the CLI
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py list

# pass script args through directly
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py audit role --json
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py tooling routes clients

# run a numbered interactive option directly, using the 1-based menu number
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py audit role 2

# run the full audit bundle and save timestamped JSON reports
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/run.py audit all --output reports/audit
```

```
audit
  migration      Migration chain integrity
  role           Role/auth coverage on all routes
  pagination     Missing pagination on list endpoints
  unused         Unused backend routes
  enums          Enum drift between Python and TypeScript
  schema         Dump live DB schema
  all            Run all audit checks

dev
  reset          Full dev DB reset (drop + migrate + seed)
  seed           Seed fake data
  tax-calendar   Bootstrap tax calendar
  bootstrap-user Create a user in the database

ops
  health         Health check (/health, /info, /auth/me)

tooling
  routes         List all registered routes
  openapi        Export OpenAPI schema to openapi.json
  contract       Verify openapi.json matches current app
  examples       Generate JSON_EXAMPLES.md from OpenAPI
```

The CLI always runs child scripts through `./.venv/bin/python` and fails fast if
the repo virtualenv is missing.

---

## Directory Layout

```
scripts/
├── run.py                      Main CLI menu
├── audit/
│   ├── audit_utils.py              Shared helpers (route loading, path normalization, output)
│   ├── route_audit_config.py       Config: public routes, pagination exceptions, enum map
│   ├── check_migration_chain.py
│   ├── check_role_coverage.py
│   ├── check_missing_pagination.py
│   ├── check_unused_routes.py
│   ├── check_enum_sync.py
│   ├── check_eager_annotations.py
│   └── dump_schema.py
├── dev/
│   ├── reset_dev_db.py
│   ├── seed_fake_data.py
│   ├── bootstrap_tax_calendar.py
│   └── bootstrap_user_production.py
├── ops/
│   └── health_check.py
├── tooling/
│   ├── export_openapi.py
│   ├── check_contract_sync.py
│   ├── list_routes.py
│   └── json_examples.py
```

---

## Audit Scripts

All audit scripts support:
- `--json` — output findings as JSON (used by `run.py audit all --output`)
- `--fail-on-findings` — exit 1 if any findings (for CI)

### check_migration_chain.py

Verifies the Alembic migration chain: one root, one head, no duplicate IDs, no broken references, no merge points.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_migration_chain.py
```

### check_role_coverage.py

Finds endpoints missing `require_role()` or `get_current_user()`. Public routes configured in `route_audit_config.py`.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_role_coverage.py
```

### check_missing_pagination.py

Finds `GET` list endpoints without `page`/`page_size`/`limit` params. Exceptions configured in `route_audit_config.py`.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_missing_pagination.py
```

### check_unused_routes.py

Reports backend routes not referenced in frontend endpoint files or the known-external config.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_unused_routes.py
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_unused_routes.py --backend-only
```

### check_enum_sync.py

Compares Python `str, Enum` values against frontend `as const` arrays. Mapping in `route_audit_config.py:ENUM_SYNC_MAP`.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_enum_sync.py
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_enum_sync.py --enum VatType
```

### check_eager_annotations.py

Finds annotations that raise `NameError` on Render's Python 3.13 but not on local 3.14, where PEP 649 defers evaluation — typically a `TYPE_CHECKING`-only import used in a runtime-evaluated annotation. CI runs 3.13.4, so a plain import catches these; this script exists to catch them locally before pushing. Fix is `from __future__ import annotations` in the reported file.

```bash
APP_ENV=test JWT_SECRET=x ./.venv/bin/python scripts/audit/check_eager_annotations.py
```

### dump_schema.py

Dumps actual DB schema (tables, columns, indexes, FKs, constraints) via SQLAlchemy `inspect()`.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/dump_schema.py
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/dump_schema.py --table client_records
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/dump_schema.py --json
```

---

## Dev Scripts

### reset_dev_db.py

Full dev reset: drop schema → delete migrations → autogenerate fresh migration → `alembic upgrade head` → `alembic check` → seed.

> **⚠️ Production warning:** Squashing migrations here will break the next deploy if production has existing migration history. Reset production manually before deploying.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py --yes
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py --yes --clients 20
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/reset_dev_db.py --yes --preserve-users
```

### seed_fake_data.py

Populates the local DB with fake coherent demo data.

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/seed_fake_data.py --reset
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/seed_fake_data.py --reset --onboarding-only
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/seed_fake_data.py --reset --preserve-users
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/dev/seed_fake_data.py --reset --reference-date 2026-05-03
```

### bootstrap_tax_calendar.py / bootstrap_user_production.py

See inline docstrings. Both are safe to run on dev or prod.

---

## Ops Scripts

### health_check.py

Hits `/health`, `/info`, and optionally `POST /auth/login` + `GET /auth/me`.

```bash
./.venv/bin/python scripts/ops/health_check.py
HEALTH_EMAIL=admin@example.com HEALTH_PASSWORD=secret ./.venv/bin/python scripts/ops/health_check.py
```

---

## Tooling Scripts

```bash
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/tooling/export_openapi.py
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/tooling/check_contract_sync.py
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/tooling/list_routes.py [filter]
APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/tooling/json_examples.py
```

---

## Configuration

`scripts/audit/route_audit_config.py` controls all audit exceptions:

| Variable | Used by |
|---|---|
| `PUBLIC_ROUTES` | `check_role_coverage.py` |
| `NO_PAGINATION_EXCEPTIONS` / `NON_LIST_SUFFIXES` | `check_missing_pagination.py` |
| `KNOWN_EXTERNAL_OR_MANUAL_ROUTES` | `check_unused_routes.py` |
| `ENUM_SYNC_MAP` / `ENUM_BACKEND_ONLY` | `check_enum_sync.py` |
