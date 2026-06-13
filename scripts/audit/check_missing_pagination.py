#!/usr/bin/env python3
"""Find list endpoints missing pagination parameters.

Identifies GET endpoints that appear to return collections but lack
page/page_size/limit parameters. Uses the live FastAPI app for accurate
parameter inspection.

Exceptions are configured in route_audit_config.py.

Usage:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_missing_pagination.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_missing_pagination.py --json
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_missing_pagination.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

from audit_utils import (  # noqa: E402  # type: ignore[import]
    add_common_args,
    err,
    header,
    normalize_path,
    ok,
    print_findings,
)
from route_audit_config import (  # noqa: E402  # type: ignore[import]
    NO_PAGINATION_EXCEPTIONS,
    NON_LIST_SUFFIXES,
)

# Parameter names that indicate pagination is present
PAGINATION_PARAMS = {"page", "page_size", "limit", "offset", "per_page"}


def _has_pagination(route) -> bool:  # type: ignore[no-untyped-def]
    endpoint = getattr(route, "endpoint", None)
    if not endpoint:
        return False
    try:
        sig = inspect.signature(endpoint)
    except ValueError, TypeError:
        return False
    return any(p.lower() in PAGINATION_PARAMS for p in sig.parameters)


def _looks_like_list(path: str) -> bool:
    """Heuristic: path likely returns a collection."""
    norm = normalize_path(path)

    # Ends with a param → single resource
    if norm.endswith("{param}"):
        return False

    # Known non-list suffixes
    for suffix in NON_LIST_SUFFIXES:
        if norm.endswith(suffix):
            return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Check pagination on list endpoints")
    add_common_args(parser)
    args = parser.parse_args()

    header("Pagination Coverage Check")

    from app.main import app  # type: ignore[import]

    findings = []
    checked = 0

    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path or "GET" not in methods:
            continue

        norm = normalize_path(path)
        key = ("GET", norm)

        if key in NO_PAGINATION_EXCEPTIONS:
            continue

        # Skip FastAPI built-ins and infra paths
        if path in (
            "/",
            "/ready",
            "/health",
            "/info",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/docs/oauth2-redirect",
        ):
            continue

        if not _looks_like_list(path):
            continue

        checked += 1

        if not _has_pagination(route):
            findings.append(
                {
                    "location": f"GET {path}",
                    "message": "Looks like a list endpoint but has no pagination params "
                    "(page/page_size/limit). Add to NO_PAGINATION_EXCEPTIONS if intentional.",
                }
            )

    if not args.json:
        if findings:
            for f in findings:
                err(f"{f['location']}: {f['message']}")
        else:
            ok(f"All {checked} candidate list endpoints have pagination.")

    print_findings(findings, as_json=args.json, label="endpoints missing pagination")

    if findings and args.fail_on_findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
