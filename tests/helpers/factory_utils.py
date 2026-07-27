from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

TEST_TAX_YEAR = 2026
TEST_DUE_DATE = date(TEST_TAX_YEAR, 2, 15)
TEST_DATETIME = datetime(TEST_TAX_YEAR, 1, 1)


class ClientRef(Protocol):
    id: int
    legal_entity_id: int


def resolve_exclusive(one: object | None, other: object | None, *, names: str) -> None:
    if one is not None and other is not None:
        raise ValueError(f"Pass either {names}, not both")


def sequence_period(sequence: int, *, start_year: int = TEST_TAX_YEAR) -> str:
    year = start_year + (sequence - 1) // 12
    month = (sequence - 1) % 12 + 1
    return f"{year}-{month:02d}"
