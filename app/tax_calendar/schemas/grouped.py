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


class TaxCalendarGroupItem(BaseModel):
    source_type: str
    source_id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str | None = None
    id_number: str | None = None
    period: str | None = None
    period_months_count: int | None = None
    tax_year: int | None = None
    status: str
    regulatory_due_date: date
    effective_due_date: date
    done: bool
    overdue: bool


class TaxCalendarGroupItemsResponse(PaginatedResponse[TaxCalendarGroupItem]):
    tax_calendar_entry_id: int
    obligation_type: str


class TaxCalendarGroupsSummary(BaseModel):
    groups: int
    linked: int
    open: int
    overdue: int
    done: int


class TaxCalendarGroupListResponse(PaginatedResponse[TaxCalendarGroupResponse]):
    summary: TaxCalendarGroupsSummary
