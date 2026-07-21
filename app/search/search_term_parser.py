"""Pure classification of the typed search term into branch-activation capabilities.

The parser is capability-based, not exclusive: a period-shaped term activates the
period branches *and* the plain-text branches (a filename can legitimately be
`2026-03`), while a bare integer activates only the user-visible identifier
branches (D4) — internal DB ids never participate, and free-text columns are not
compared against bare numbers.

Lives in one place so the frontend never classifies; it sends the trimmed term as-is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SLASH_PERIOD = re.compile(r"^(\d{1,2})/(\d{4})$")
_DB_PERIOD = re.compile(r"^(\d{4})-(\d{2})$")
_BARE_INTEGER = re.compile(r"^\d+$")

# Postgres INTEGER bound: a larger literal in an `id == term` comparison would
# error at execution time, so oversized digit runs carry no integer capability.
_MAX_INT32 = 2**31 - 1

_MIN_PLAUSIBLE_YEAR = 1990
_MAX_PLAUSIBLE_YEAR = 2100


@dataclass(frozen=True)
class ParsedSearchTerm:
    """What the trimmed term can match, expressed as independent capabilities."""

    raw: str
    period: str | None = None
    integer: int | None = None
    tax_year: int | None = None
    activates_text: bool = True


def _normalized_period(term: str) -> str | None:
    slash = _SLASH_PERIOD.match(term)
    if slash:
        month, year = int(slash.group(1)), slash.group(2)
        if 1 <= month <= 12:
            return f"{year}-{month:02d}"
        return None
    db_form = _DB_PERIOD.match(term)
    if db_form:
        if 1 <= int(db_form.group(2)) <= 12:
            return term
        return None
    return None


def parse_search_term(term: str) -> ParsedSearchTerm:
    """Classify `term` (already trimmed by the API layer) into capabilities."""
    period = _normalized_period(term)
    if period is not None:
        return ParsedSearchTerm(raw=term, period=period)

    if _BARE_INTEGER.match(term):
        value = int(term)
        integer = value if value <= _MAX_INT32 else None
        tax_year = value if _MIN_PLAUSIBLE_YEAR <= value <= _MAX_PLAUSIBLE_YEAR else None
        # A bare number is an identifier, never free text (D4): identifier-string
        # columns (binder number, ITA reference) still compare against the raw
        # digits, but titles, filenames and recipients do not.
        return ParsedSearchTerm(raw=term, integer=integer, tax_year=tax_year, activates_text=False)

    return ParsedSearchTerm(raw=term)


__all__ = ["ParsedSearchTerm", "parse_search_term"]
