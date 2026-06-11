from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether committed openapi.json matches the current FastAPI app."
    )
    parser.add_argument(
        "--path",
        default="openapi.json",
        help="Path to OpenAPI JSON file. Defaults to ./openapi.json.",
    )
    return parser.parse_args()


def normalized_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    args = parse_args()
    openapi_path = Path(args.path)

    if not openapi_path.is_file():
        print(f"OpenAPI file not found: {openapi_path}", file=sys.stderr)
        return 1

    try:
        actual = json.loads(openapi_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {openapi_path}: {exc}", file=sys.stderr)
        return 1

    expected = app.openapi()

    if normalized_json(expected) != normalized_json(actual):
        print(
            f"{openapi_path} is out of sync. Run scripts/tooling/export_openapi.py and review the diff.",
            file=sys.stderr,
        )
        return 1

    print(f"{openapi_path} is in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
