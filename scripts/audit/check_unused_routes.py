#!/usr/bin/env python3
"""Report backend routes not referenced in the frontend or known external callers.

Strategy:
  1. Load all backend routes from the live FastAPI app.
  2. Extract frontend endpoint patterns from src/api/core-endpoints.ts
     and src/features/**/api/endpoints.ts.
  3. Normalize both sides (replace {param}/${param} with {param}).
  4. Match backend routes against frontend patterns.
  5. Fallback: grep all TS files for path-like strings that weren't in endpoint files.
  6. Routes in KNOWN_EXTERNAL_OR_MANUAL_ROUTES are always considered used.
  7. Report unmatched routes as unused candidates.

Usage:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_unused_routes.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_unused_routes.py --json
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_unused_routes.py --backend-only
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_unused_routes.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

from audit_utils import (  # noqa: E402  # type: ignore[import]
    FRONTEND_SRC,
    add_common_args,
    extract_frontend_paths,
    header,
    load_app_routes,
    normalize_path,
    ok,
    print_findings,
    warn,
)
from route_audit_config import KNOWN_EXTERNAL_OR_MANUAL_ROUTES  # noqa: E402  # type: ignore[import]

# Paths to skip entirely (FastAPI built-ins, OpenAPI)
SKIP_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
SKIP_PREFIXES = ("/docs/", "/redoc/")


def _fallback_grep_paths(already_found: set[str]) -> set[str]:
    """Grep all TS files for path-like strings not in endpoint files."""
    _PATH_RE = re.compile(r'["\x60](/(?:api/v1|sign|health|info)[^"\x60\n\s]+)["\x60]')
    extra: set[str] = set()
    for f in FRONTEND_SRC.rglob("*.ts"):
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _PATH_RE.finditer(text):
            p = m.group(1)
            if normalize_path(p) not in already_found:
                extra.add(p)
    return extra


def main() -> None:
    parser = argparse.ArgumentParser(description="Find backend routes unused by the frontend")
    add_common_args(parser)
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Only check backend-to-backend calls (skip frontend search)",
    )
    args = parser.parse_args()

    header("Unused Routes Check")

    backend_routes = load_app_routes()
    print(f"  Backend routes: {len(backend_routes)}")

    # Build set of normalized frontend paths
    if not args.backend_only:
        frontend_raw = extract_frontend_paths()
        frontend_norm: set[str] = {normalize_path(p) for p in frontend_raw}
        print(f"  Frontend endpoint patterns: {len(frontend_norm)}")

        # Fallback grep
        fallback_raw = _fallback_grep_paths(frontend_norm)
        fallback_norm: set[str] = {normalize_path(p) for p in fallback_raw}
        frontend_norm |= fallback_norm
        if fallback_norm:
            print(f"  Additional patterns from grep: {len(fallback_norm)}")
    else:
        frontend_norm = set()

    # Build set of known external routes (normalized)
    known_norm: set[str] = {normalize_path(p) for _, p in KNOWN_EXTERNAL_OR_MANUAL_ROUTES}

    findings = []
    skipped = 0

    for route in backend_routes:
        path = route["path"]
        method = route["method"]
        norm = normalize_path(path)

        # Skip built-ins
        if path in SKIP_PATHS or any(path.startswith(p) for p in SKIP_PREFIXES):
            skipped += 1
            continue

        # Known external
        if norm in known_norm:
            continue

        # Match against frontend
        if norm in frontend_norm:
            continue

        findings.append(
            {
                "location": f"{method} {path}",
                "message": "Not found in frontend endpoint files or known external routes",
            }
        )

    if not args.json:
        if findings:
            for f in findings:
                warn(f"{f['location']}: {f['message']}")
        else:
            ok("All backend routes are referenced in the frontend or known-external config.")

    print_findings(findings, as_json=args.json, label="unused route candidates")

    if findings:
        if not args.json:
            print(
                "\n  Tip: If a route is used but not detected, add it to\n"
                "  KNOWN_EXTERNAL_OR_MANUAL_ROUTES in scripts/route_audit_config.py"
            )

    if findings and args.fail_on_findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
