"""Shared utilities for route and code audit scripts."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# FastAPI route loading
# ---------------------------------------------------------------------------


def load_app_routes() -> list[dict[str, str]]:
    """Return all registered FastAPI routes as {method, path} dicts.

    Loads app.main:app — requires APP_ENV + ENV_FILE to be set.
    """
    _setup_env()
    from app.main import app  # type: ignore[import]

    routes = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path:
            for method in methods:
                routes.append({"method": method.upper(), "path": path})
    return routes


def _setup_env() -> None:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("JWT_SECRET", "dev-seed-secret")
    env_file = ROOT_DIR / ".env.development"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    # Redirect all logging to stderr so --json output stays clean
    import logging

    logging.basicConfig(stream=sys.stderr)


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

_PARAM_RE = re.compile(r"\{[^}]+\}")  # FastAPI {param}
_TS_PARAM_RE = re.compile(r"\$\{[^}]+\}")  # TS template ${param}
_TRAILING_SLASH = re.compile(r"/+$")


def normalize_path(path: str) -> str:
    """Replace all dynamic segments with {param} and strip trailing slash."""
    path = _PARAM_RE.sub("{param}", path)
    path = _TS_PARAM_RE.sub("{param}", path)
    path = _TRAILING_SLASH.sub("", path)
    return path


def paths_match(backend_path: str, frontend_path: str) -> bool:
    """Return True if normalized paths are equal."""
    return normalize_path(backend_path) == normalize_path(frontend_path)


# ---------------------------------------------------------------------------
# Frontend endpoint extraction
# ---------------------------------------------------------------------------

FRONTEND_ROOT = ROOT_DIR.parent / "frontend"
FRONTEND_SRC = FRONTEND_ROOT / "src"

_STRING_LITERAL_RE = re.compile(r"['\"`]([^'\"`\n]+)['\"`]")
_TEMPLATE_PATH_RE = re.compile(r"`([^`\n]*\$\{[^`\n]*)`")


def extract_frontend_paths() -> list[str]:
    """Extract all URL path patterns from frontend endpoint files.

    Searches:
      - src/api/core-endpoints.ts
      - src/features/**/api/endpoints.ts
      - src/features/**/api.ts
      - src/features/**/api/**/*.ts
    """
    files: list[Path] = []
    core = FRONTEND_SRC / "api" / "core-endpoints.ts"
    if core.exists():
        files.append(core)
    files.extend(sorted(FRONTEND_SRC.glob("features/**/api/endpoints.ts")))
    files.extend(sorted(FRONTEND_SRC.glob("features/**/api.ts")))
    files.extend(sorted(FRONTEND_SRC.glob("features/**/api/**/*.ts")))
    files = sorted(set(files))

    paths: set[str] = set()
    for f in files:
        text = f.read_text(encoding="utf-8")
        # static strings
        for m in _STRING_LITERAL_RE.finditer(text):
            val = m.group(1)
            if val.startswith("/") and not val.startswith("//"):
                paths.add(val)
        # template literals with params
        for m in _TEMPLATE_PATH_RE.finditer(text):
            val = m.group(1)
            if val.startswith("/"):
                paths.add(val)

    # Prepend /api/v1 to paths that don't already have it and aren't public
    normalized: list[str] = []
    for p in paths:
        if p.startswith("/api/") or p in {"/", "/health", "/info"} or p.startswith("/sign/"):
            normalized.append(p)
        else:
            normalized.append("/api/v1" + p)
    return normalized


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

RESET = "\033[0m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BOLD = "\033[1m"
DIM = "\033[2m"


def ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠{RESET}  {msg}")


def err(msg: str) -> None:
    print(f"{RED}✗{RESET} {msg}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}")


def print_findings(
    findings: list[dict[str, Any]],
    *,
    as_json: bool = False,
    label: str = "findings",
) -> None:
    if as_json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
    else:
        for f in findings:
            loc = f.get("location", "")
            msg = f.get("message", "")
            loc_str = f"{DIM}{loc}{RESET} " if loc else ""
            print(f"  {loc_str}{msg}")
    if findings:
        print(f"\n{BOLD}{len(findings)} {label}{RESET}")
    else:
        print(f"\n{GREEN}No {label} found.{RESET}")


# ---------------------------------------------------------------------------
# Shared arg helpers
# ---------------------------------------------------------------------------


def add_common_args(parser: Any) -> None:
    """Add --json and --fail-on-findings to any argparse parser."""
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit with code 1 if any findings are reported",
    )
