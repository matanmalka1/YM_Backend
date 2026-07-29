from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def utcnow() -> datetime:
    """
    Return the current UTC time as a naive datetime.

    The codebase currently persists naive UTC timestamps in the database
    (SQLAlchemy `DateTime` without `timezone=True`). We derive the value from a
    timezone-aware UTC timestamp to avoid `datetime.utcnow()` deprecations.
    """

    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_aware() -> datetime:
    """
    Return the current UTC time as a timezone-aware datetime.

    Use this for columns declared as DateTime(timezone=True).
    """

    return datetime.now(UTC)


def israel_today() -> date:
    return datetime.now(ISRAEL_TZ).date()


def israel_date(dt: datetime) -> date:
    """The Israel-local calendar date of a naive-UTC timestamp.

    Deadlines are Israel dates; reading a UTC timestamp's ``.date()`` against one
    misreads the two hours around midnight.
    """

    return dt.replace(tzinfo=UTC).astimezone(ISRAEL_TZ).date()


def start_of_day(d: date) -> datetime:
    """Naive midnight at the start of ``d``.

    Used for `created_after`/`created_before`-style filtering of naive UTC
    `DateTime` columns against `date` query params: `column >= start_of_day(d)`.
    """

    return datetime(d.year, d.month, d.day)


def start_of_next_day(d: date) -> datetime:
    """Naive midnight at the start of the day after ``d``.

    Used for half-open upper bounds: `column < start_of_next_day(d)` includes the
    whole of `d`.
    """

    return start_of_day(d) + timedelta(days=1)
