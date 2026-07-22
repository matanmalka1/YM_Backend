from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class TaxCalendarWarning(BaseModel):
    code: Literal["count_mismatch", "registry_data_missing", "bootstrap_count_mismatch"]
    year: int | None = None
    obligation_type: str | None = None
    expected: int | None = None
    found: int | None = None
    tax_year_after: int | None = None
    tax_year_before: int | None = None
    expected_per_year: int | None = None


class DeadlineRuleResponse(BaseModel):
    id: int
    rule_type: str
    due_day_of_month: int
    offset_months: int
    effective_from: date
    effective_to: date | None = None
    description: str | None = None

    model_config = {"from_attributes": True}


class TaxCalendarEntryResponse(BaseModel):
    id: int
    obligation_type: str
    period: str | None = None
    period_months_count: int | None = None
    tax_year: int
    due_date: date
    deadline_rule_id: int

    model_config = {"from_attributes": True}


class TaxCalendarSummaryResponse(BaseModel):
    tax_year_after: int | None = None
    tax_year_before: int | None = None
    total_entries: int
    per_year: dict[int, dict[str, int]]
    warnings: list[TaxCalendarWarning]


class TaxCalendarBootstrapRequest(BaseModel):
    tax_year_after: int
    tax_year_before: int


class TaxCalendarBootstrapResponse(BaseModel):
    tax_year_after: int
    tax_year_before: int
    rules_created: int
    rules_skipped: int
    rules_by_type: dict[str, str]
    entries_created: int
    entries_skipped: int
    total_entries_for_range: int
    warnings: list[TaxCalendarWarning]
