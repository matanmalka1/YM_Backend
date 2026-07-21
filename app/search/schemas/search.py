import datetime as dt
from enum import Enum as PyEnum

from pydantic import BaseModel, Field

from app.core.api_types import ApiDecimal, PaginatedResponse


class SearchMatchType(str, PyEnum):
    """Entity types that appear as match rows.

    Deliberately excludes `client`: a client is a resolution result, not a record row.
    Every member is also a `LinkedEntity`, which owns the route each row links to.
    """

    BINDER = "binder"
    DOCUMENT = "document"
    VAT_WORK_ITEM = "vat_work_item"
    ANNUAL_REPORT = "annual_report"
    ADVANCE_PAYMENT = "advance_payment"
    CHARGE = "charge"
    TASK = "task"
    NOTIFICATION = "notification"


class SearchClientMatch(BaseModel):
    """A client the typed term resolved to."""

    id: int
    office_client_number: int | None = None
    name: str
    id_number: str | None = None
    status: str
    matched_binder_numbers: list[str] = Field(default_factory=list)
    href: str


class SearchMatch(BaseModel):
    """One record the typed term matched, carrying its owning client's identity.

    A match row is meaningless without its client, so every row names it. `status` is
    nullable because documents carry no work status. `amount` is set only by the
    money-carrying types. `occurred_on` is the date the row is anchored to (due date,
    upload date, issue date), so a type's matches read chronologically.
    """

    result_type: SearchMatchType
    id: int
    title: str
    detail: str | None = None
    status: str | None = None
    amount: ApiDecimal | None = None
    occurred_on: dt.date | None = None
    href: str
    client_record_id: int
    client_name: str
    client_office_number: int | None = None


class SearchMatchGroup(BaseModel):
    """Preview rows for one type plus the exact total behind them."""

    items: list[SearchMatch] = Field(default_factory=list)
    total: int = 0


class SearchMatchGroups(BaseModel):
    binders: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    documents: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    vat_work_items: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    annual_reports: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    advance_payments: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    charges: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    tasks: SearchMatchGroup = Field(default_factory=SearchMatchGroup)
    notifications: SearchMatchGroup = Field(default_factory=SearchMatchGroup)


class SearchResponse(BaseModel):
    """Client resolution plus the record matches, side by side."""

    clients: PaginatedResponse[SearchClientMatch]
    matches: SearchMatchGroups = Field(default_factory=SearchMatchGroups)
