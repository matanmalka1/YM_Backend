import datetime as dt
from enum import Enum as PyEnum

from pydantic import BaseModel, Field

from app.core.api_types import ApiDecimal, PaginatedResponse


class SearchItemType(str, PyEnum):
    """Entity types that appear as rows in a client's item feed.

    Deliberately excludes `client`: the client is the feed's subject, not a row in it.
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
    """A client the typed term resolved to, offered for selection."""

    id: int
    office_client_number: int | None = None
    name: str
    id_number: str | None = None
    status: str
    matched_binder_numbers: list[str] = Field(default_factory=list)
    href: str


class SearchItem(BaseModel):
    """One item belonging to the selected client, in the one shape every type shares.

    `status` is nullable because documents carry no work status; their type is shown
    in its place. `amount` is set only by the money-carrying types. `occurred_on` is the
    date the row is anchored to (due date, upload date, issue date), so a mixed feed can
    be read chronologically.
    """

    result_type: SearchItemType
    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str
    title: str
    detail: str | None = None
    status: str | None = None
    amount: ApiDecimal | None = None
    occurred_on: dt.date | None = None
    href: str


class SearchItemGroup(BaseModel):
    """Preview rows for one type plus the exact total behind them."""

    items: list[SearchItem] = Field(default_factory=list)
    total: int = 0


class SearchItemGroups(BaseModel):
    binders: SearchItemGroup = Field(default_factory=SearchItemGroup)
    documents: SearchItemGroup = Field(default_factory=SearchItemGroup)
    vat_work_items: SearchItemGroup = Field(default_factory=SearchItemGroup)
    annual_reports: SearchItemGroup = Field(default_factory=SearchItemGroup)
    advance_payments: SearchItemGroup = Field(default_factory=SearchItemGroup)
    charges: SearchItemGroup = Field(default_factory=SearchItemGroup)
    tasks: SearchItemGroup = Field(default_factory=SearchItemGroup)
    notifications: SearchItemGroup = Field(default_factory=SearchItemGroup)


class SearchResponse(BaseModel):
    """Both search phases in one payload: which client, then everything of that client."""

    clients: PaginatedResponse[SearchClientMatch]
    items: SearchItemGroups = Field(default_factory=SearchItemGroups)
