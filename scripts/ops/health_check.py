#!/usr/bin/env python3
"""Hit key endpoints and report status.

Checks:
  GET  /health
  GET  /info
  POST /api/v1/auth/login  (optional — requires --email + --password or env vars)
  GET  /api/v1/auth/me     (only if login succeeds)

Usage:
    ./.venv/bin/python scripts/ops/health_check.py
    ./.venv/bin/python scripts/ops/health_check.py --url http://localhost:8000
    ./.venv/bin/python scripts/ops/health_check.py --email admin@example.com --password secret
    HEALTH_EMAIL=admin@example.com HEALTH_PASSWORD=secret ./.venv/bin/python scripts/ops/health_check.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

TIMEOUT = 8


def _request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body else None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:
        return 0, str(exc)


def _status_line(label: str, status: int, ok_range: tuple[int, int] = (200, 299)) -> bool:
    if ok_range[0] <= status <= ok_range[1]:
        color = GREEN
        icon = "✓"
        passed = True
    else:
        color = RED
        icon = "✗"
        passed = False
    status_str = str(status) if status else "connection failed"
    print(f"  {color}{icon}{RESET}  {label:<35} {color}{status_str}{RESET}")
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check key API endpoints")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL (default: http://localhost:8000)"
    )
    parser.add_argument("--email", default=os.environ.get("HEALTH_EMAIL", ""), help="Login email")
    parser.add_argument(
        "--password", default=os.environ.get("HEALTH_PASSWORD", ""), help="Login password"
    )
    args = parser.parse_args()

    base = args.url.rstrip("/")
    failures = 0

    print(f"\n{BOLD}Health Check — {base}{RESET}\n")

    # GET /health
    status, _ = _request("GET", f"{base}/health")
    if not _status_line("GET /health", status):
        failures += 1

    # GET /info
    status, _ = _request("GET", f"{base}/info")
    if not _status_line("GET /info", status):
        failures += 1

    # Auth flow (optional)
    if args.email and args.password:
        status, body = _request(
            "POST",
            f"{base}/api/v1/auth/login",
            body={"email": args.email, "password": args.password},
        )
        if not _status_line("POST /api/v1/auth/login", status):
            failures += 1
            print(f"       {DIM}login failed — skipping /auth/me{RESET}")
        else:
            token = None
            if isinstance(body, dict):
                token = body.get("access_token")
            if token:
                status, _ = _request("GET", f"{base}/api/v1/auth/me", token=token)
                if not _status_line("GET  /api/v1/auth/me", status):
                    failures += 1
            else:
                print(
                    f"       {YELLOW}⚠{RESET}  Could not extract access_token from login response"
                )
                failures += 1
    else:
        print(f"  {DIM}--  auth check skipped (no --email/--password){RESET}")

    print()
    if failures:
        print(f"{RED}{BOLD}{failures} check(s) failed.{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}All checks passed.{RESET}")


if __name__ == "__main__":
    main()
