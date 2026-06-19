#!/usr/bin/env python3
"""Seed local/dev tax calendar defaults and generated entries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("JWT_SECRET", "dev-seed-secret")
os.environ.setdefault("APP_ENV", "development")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap tax calendar rows.")
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    from app.database import SessionLocal
    from app.tax_calendar.services.tax_calendar_bootstrap_service import bootstrap_tax_calendar

    args = _parse_args()
    db = SessionLocal()
    try:
        result = bootstrap_tax_calendar(
            db,
            start_year=args.start_year,
            end_year=args.end_year,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    if result["warnings"]:
        print("\nWARNINGS:")
        for w in result["warnings"]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
