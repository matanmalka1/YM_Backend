from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    BeforeValidator,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)

T = TypeVar("T")

# Business-required text: strips surrounding whitespace then rejects empty,
# so "" and whitespace-only ("   ") both fail validation with 422.
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _coerce_decimal(value: Any) -> Any:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, (str, int, float)):
        return str(value)
    return value


def _normalize_utc_datetime(value: Any) -> Any:
    if value is None or not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _serialize_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _serialize_datetime(value: datetime) -> str:
    normalized = _normalize_utc_datetime(value)
    return normalized.isoformat().replace("+00:00", "Z")


ApiDecimal = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    PlainSerializer(_serialize_decimal, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "decimal", "examples": ["123.45"]}),
]


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


ApiDateTime = Annotated[
    datetime,
    BeforeValidator(_normalize_utc_datetime),
    PlainSerializer(_serialize_datetime, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "format": "date-time",
            "examples": ["2026-01-02T03:04:05Z"],
        }
    ),
]
