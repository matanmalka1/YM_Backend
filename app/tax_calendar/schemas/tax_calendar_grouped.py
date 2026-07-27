from datetime import date

from pydantic import BaseModel

from app.core.api_types import PaginatedResponse


class TaxCalendarGroupResponse(BaseModel):
    tax_calendar_entry_id: int
    obligation_type: str
    period: str | None = None
    period_months_count: int | None = None
    tax_year: int
    # Null for annual obligations. A shared regulatory date exists only where one
    # statutory date genuinely applies to every client — true for a VAT or advance
    # period, false for an annual report, whose deadline is derived per entity type
    # onto AnnualReport.filing_deadline. See docs/domains/tax-calendar.md.
    regulatory_due_date: date | None = None
    # Null when no linked row has a known deadline — an empty annual group, or one
    # whose reports all carry a custom (unset) filing deadline.
    effective_due_date_min: date | None = None
    effective_due_date_max: date | None = None
    linked_count: int
    open_count: int
    done_count: int
    overdue_count: int


class TaxCalendarGroupsSummary(BaseModel):
    groups: int
    linked: int
    open: int
    overdue: int
    done: int


class TaxCalendarGroupListResponse(PaginatedResponse[TaxCalendarGroupResponse]):
    summary: TaxCalendarGroupsSummary
