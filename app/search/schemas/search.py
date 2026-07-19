from typing import Literal

from pydantic import BaseModel, Field

from app.core.api_types import ApiDecimal


class SearchResult(BaseModel):
    """Single search result."""

    result_type: Literal["client", "binder"]
    client_record_id: int
    office_client_number: int | None = None
    client_name: str
    id_number: str | None = None
    client_status: str | None = None
    binder_id: int | None = None
    binder_number: str | None = None


class DocumentSearchResult(BaseModel):
    """Single document search result."""

    id: int
    client_record_id: int
    office_client_number: int | None = None
    client_name: str
    business_id: int | None = None
    business_name: str | None = None
    document_type: str
    original_filename: str | None = None
    tax_year: int | None = None


class OperationalSearchItem(BaseModel):
    result_type: Literal["task", "vat_work_item", "annual_report", "charge", "advance_payment"]
    id: int
    client_record_id: int
    office_client_number: int
    client_name: str
    title: str
    detail: str | None = None
    status: str
    amount: ApiDecimal | None = None
    href: str


class OperationalSearchGroup(BaseModel):
    items: list[OperationalSearchItem] = Field(default_factory=list)
    total: int = 0


class OperationalSearchResults(BaseModel):
    tasks: OperationalSearchGroup = Field(default_factory=OperationalSearchGroup)
    vat_work_items: OperationalSearchGroup = Field(default_factory=OperationalSearchGroup)
    annual_reports: OperationalSearchGroup = Field(default_factory=OperationalSearchGroup)
    charges: OperationalSearchGroup = Field(default_factory=OperationalSearchGroup)
    advance_payments: OperationalSearchGroup = Field(default_factory=OperationalSearchGroup)


class SearchResponse(BaseModel):
    """Search results response."""

    results: list[SearchResult]
    documents: list[DocumentSearchResult] = Field(default_factory=list)
    operational: OperationalSearchResults = Field(default_factory=OperationalSearchResults)
    page: int
    page_size: int
    total: int
