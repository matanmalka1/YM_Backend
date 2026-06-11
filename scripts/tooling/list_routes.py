from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from fastapi.routing import APIRoute

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List FastAPI routes.")
    parser.add_argument(
        "filter",
        nargs="?",
        help="Optional substring filter matched against route path, name, method, or tags.",
    )
    return parser.parse_args()


def route_tags(route: APIRoute) -> str:
    return ", ".join(str(tag) for tag in route.tags)


def route_methods(route: APIRoute) -> list[str]:
    return sorted((route.methods or set()) - {"HEAD", "OPTIONS"})


def route_matches(route: APIRoute, route_filter: str | None) -> bool:
    if not route_filter:
        return True

    value = route_filter.lower()
    haystack: Iterable[str] = (
        route.path.lower(),
        (route.name or "").lower(),
        route_tags(route).lower(),
        " ".join(route_methods(route)).lower(),
    )
    return any(value in item for item in haystack)


def main() -> None:
    args = parse_args()

    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route_matches(route, args.filter)
    ]
    routes.sort(key=lambda route: (route.path, route_methods(route), route.name or ""))

    for route in routes:
        methods = ", ".join(route_methods(route))
        print(f"{methods:<12} {route.path:<70} {route.name or '-'}")


if __name__ == "__main__":
    main()
