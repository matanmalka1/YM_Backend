from datetime import date

from pydantic import BaseModel

from app.core.api_types import PaginatedResponse


class TaxCalendarGroupResponse(BaseModel):
    tax_calendar_entry_id: int
    obligation_type: str
    period: str | None = None
    period_months_count: int | None = None
    tax_year: int
    regulatory_due_date: date
    effective_due_date_min: date
    effective_due_date_max: date
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
