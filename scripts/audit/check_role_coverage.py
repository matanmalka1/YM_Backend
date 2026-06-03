#!/usr/bin/env python3
"""Find API endpoints missing require_role() or get_current_user() protection.

Loads the live FastAPI app and inspects each route's dependency chain.
Reports routes that have neither require_role nor get_current_user,
unless they are listed in PUBLIC_ROUTES or AUTH_ONLY_ROUTES in route_audit_config.py.

Usage:
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_role_coverage.py
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_role_coverage.py --json
    APP_ENV=development ENV_FILE=.env.development ./.venv/bin/python scripts/audit/check_role_coverage.py --fail-on-findings
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_AUDIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SCRIPTS_AUDIT_DIR))

from audit_utils import add_common_args, err, header, ok, print_findings  # type: ignore[import]
from route_audit_config import AUTH_ONLY_ROUTES, PUBLIC_ROUTES  # type: ignore[import]


def _get_dependency_names(route) -> set[str]:  # type: ignore[no-untyped-def]
    """Collect all dependency function names recursively for a route."""
    names: set[str] = set()

    def _collect(deps):  # type: ignore[no-untyped-def]
        for dep in deps:
            fn = getattr(dep, "dependency", None) or dep
            fn_name = getattr(fn, "__name__", "") or getattr(fn, "__qualname__", "") or ""
            names.add(fn_name)
            # recurse into sub-dependencies
            sub_deps = getattr(fn, "dependencies", None) or []
            _collect(sub_deps)

    route_deps = list(getattr(route, "dependencies", None) or [])
    endpoint = getattr(route, "endpoint", None)
    if endpoint:
        import inspect

        sig = inspect.signature(endpoint)
        for param in sig.parameters.values():
            annotation = param.annotation
            if hasattr(annotation, "__metadata__"):
                for meta in annotation.__metadata__:
                    dep_fn = getattr(meta, "dependency", None)
                    if dep_fn:
                        dep_name = (
                            getattr(dep_fn, "__name__", "")
                            or getattr(dep_fn, "__qualname__", "")
                            or ""
                        )
                        names.add(dep_name)
                        sub = getattr(dep_fn, "dependencies", None) or []
                        _collect(sub)
    _collect(route_deps)
    return names


def _is_auth_protected(dep_names: set[str]) -> tuple[bool, bool]:
    """Return (has_role_check, has_auth_check)."""
    has_role = any("require_role" in n or "role_checker" in n for n in dep_names)
    has_auth = has_role or any("get_current_user" in n or "CurrentUser" in n for n in dep_names)
    return has_role, has_auth


def main() -> None:
    parser = argparse.ArgumentParser(description="Check require_role coverage on all API routes")
    add_common_args(parser)
    args = parser.parse_args()

    header("Role Coverage Check")

    from app.main import app  # type: ignore[import]

    findings = []
    routes_checked = 0

    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue

        for method in methods:
            method = method.upper()
            key = (method, path)
            routes_checked += 1

            if key in PUBLIC_ROUTES:
                continue
            if key in AUTH_ONLY_ROUTES:
                continue

            dep_names = _get_dependency_names(route)
            has_role, has_auth = _is_auth_protected(dep_names)

            if not has_auth:
                findings.append(
                    {
                        "location": f"{method} {path}",
                        "message": "No auth dependency found (missing require_role or get_current_user)",
                    }
                )
            elif not has_role:
                findings.append(
                    {
                        "location": f"{method} {path}",
                        "message": "Has get_current_user but no require_role — intentional? Add to AUTH_ONLY_ROUTES if so",
                    }
                )

    if not args.json:
        if findings:
            for f in findings:
                err(f"{f['location']}: {f['message']}")
        else:
            ok(f"All {routes_checked} checked routes have auth protection.")

    print_findings(findings, as_json=args.json, label="unprotected routes")

    if findings and args.fail_on_findings:
        sys.exit(1)


if __name__ == "__main__":
    main()
