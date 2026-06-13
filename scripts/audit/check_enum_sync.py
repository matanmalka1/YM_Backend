#!/usr/bin/env python3
"""Compare Python enums against their frontend TypeScript counterparts.

Uses ENUM_SYNC_MAP in route_audit_config.py as the explicit mapping.
For each mapped enum, extracts values from the Python class and the TS
`as const` array, then reports mismatches and missing values.

Also reports Python enums not covered by the map (as informational warnings).

Usage:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_enum_sync.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_enum_sync.py --json
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_enum_sync.py --fail-on-findings
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_enum_sync.py --enum VatType
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from enum import EnumMeta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

from audit_utils import (  # noqa: E402  # type: ignore[import]
    FRONTEND_SRC,
    add_common_args,
    err,
    header,
    ok,
    print_findings,
    warn,
)
from route_audit_config import (  # noqa: E402  # type: ignore[import]
    ENUM_BACKEND_ONLY,
    ENUM_SYNC_MAP,
)

_SETUP_DONE = False


def _setup_env() -> None:
    global _SETUP_DONE
    if _SETUP_DONE:
        return
    import os

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("JWT_SECRET", "dev-seed-secret")
    env_file = ROOT_DIR / ".env.development"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    _SETUP_DONE = True


# ---------------------------------------------------------------------------
# Python enum discovery
# ---------------------------------------------------------------------------

_ENUM_FILES = [
    "app/common/enums.py",
    "app/clients/enums.py",
    "app/vat/models/vat_enums.py",
    "app/users/models/user.py",
    "app/tasks/models/task.py",
    "app/signature_requests/models/signature_request.py",
    "app/charges/models/charge.py",
    "app/notifications/models/notification.py",
    "app/authority_contacts/models/authority_contact.py",
    "app/businesses/models/business.py",
    "app/documents/permanent_documents/models/permanent_document.py",
    "app/clients/models/person_legal_entity_link.py",
    "app/common/source_types.py",
    "app/users/models/user_audit_log.py",
]


def _discover_all_python_enums() -> dict[str, set[str]]:
    """Return {ClassName: {value, ...}} for all str enums in known files."""
    _setup_env()
    result: dict[str, set[str]] = {}
    for rel_path in _ENUM_FILES:
        module_path = str(Path(rel_path).with_suffix("")).replace("/", ".")
        try:
            mod = importlib.import_module(module_path)
        except Exception:
            continue
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if (
                isinstance(obj, EnumMeta)
                and issubclass(obj, str)
                and obj.__module__ == mod.__name__
            ):
                result[attr_name] = {m.value for m in obj}  # type: ignore[union-attr]
    return result


def _get_python_enum_values(enum_name: str) -> set[str] | None:
    """Support both 'ClassName' and 'module.path.ClassName' keys."""
    if "." in enum_name:
        module_path, _, class_name = enum_name.rpartition(".")
        _setup_env()
        try:
            mod = importlib.import_module(module_path)
            obj = getattr(mod, class_name, None)
            if obj is not None and isinstance(obj, EnumMeta):
                return {m.value for m in obj}  # type: ignore[union-attr]
        except Exception:
            pass
        return None
    all_enums = _discover_all_python_enums()
    return all_enums.get(enum_name)


# ---------------------------------------------------------------------------
# TypeScript array extraction
# ---------------------------------------------------------------------------

_AS_CONST_RE = re.compile(
    r"export\s+const\s+(\w+)\s*=\s*\[([^\]]+)\]\s*(?:as\s+const|satisfies)",
    re.DOTALL,
)
_STRING_VAL_RE = re.compile(r"['\"`]([^'\"`\n]+)['\"`]")


def _get_ts_array_values(file_rel: str, array_name: str) -> set[str] | None:
    """Extract values from a `as const` array in a TS file."""
    path = FRONTEND_SRC / file_rel
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    for m in _AS_CONST_RE.finditer(text):
        if m.group(1) == array_name:
            raw = m.group(2)
            return {v for v in _STRING_VAL_RE.findall(raw) if v}
    return None


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------


def _check_enum(enum_name: str, ts_ref: str) -> list[dict]:
    findings = []
    ts_file, _, ts_array = ts_ref.partition(":")

    py_values = _get_python_enum_values(enum_name)
    if py_values is None:
        findings.append(
            {
                "location": f"Python:{enum_name}",
                "message": f"Could not load Python enum {enum_name!r}",
            }
        )
        return findings

    ts_values = _get_ts_array_values(ts_file, ts_array)
    if ts_values is None:
        findings.append(
            {
                "location": f"frontend/{ts_file}:{ts_array}",
                "message": f"TS array {ts_array!r} not found in {ts_file}",
            }
        )
        return findings

    missing_in_ts = py_values - ts_values
    extra_in_ts = ts_values - py_values

    for v in sorted(missing_in_ts):
        findings.append(
            {
                "location": f"{enum_name} → {ts_array}",
                "message": f"Value {v!r} in Python but missing in TS",
            }
        )
    for v in sorted(extra_in_ts):
        findings.append(
            {
                "location": f"{ts_array} → {enum_name}",
                "message": f"Value {v!r} in TS but missing in Python enum",
            }
        )

    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Python enums against frontend TS constants"
    )
    add_common_args(parser)
    parser.add_argument("--enum", help="Check only this enum (Python class name)")
    args = parser.parse_args()

    header("Enum Sync Check")

    sync_map = ENUM_SYNC_MAP
    if args.enum:
        if args.enum not in sync_map:
            print(f"  {args.enum!r} not in ENUM_SYNC_MAP")
            sys.exit(1)
        sync_map = {args.enum: sync_map[args.enum]}

    all_findings = []

    for enum_name, ts_ref in sorted(sync_map.items()):
        findings = _check_enum(enum_name, ts_ref)
        if not args.json:
            if findings:
                for f in findings:
                    err(f"  {f['location']}: {f['message']}")
            else:
                ok(f"{enum_name} ↔ {ts_ref.split(':')[1]}")
        all_findings.extend(findings)

    # Report unmapped enums (informational)
    if not args.json and not args.enum:
        all_py = _discover_all_python_enums()
        unmapped = sorted(n for n in all_py if n not in sync_map and n not in ENUM_BACKEND_ONLY)
        if unmapped:
            print()
            for name in unmapped:
                warn(f"  {name} — not in ENUM_SYNC_MAP or ENUM_BACKEND_ONLY (add to one)")

    print_findings(all_findings, as_json=args.json, label="enum drift issues")

    if all_findings and args.fail_on_findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
