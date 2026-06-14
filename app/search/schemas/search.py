from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Single search result."""

    result_type: str  # "client" | "binder"
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


class SearchResponse(BaseModel):
    """Search results response."""

    results: list[SearchResult]
    documents: list[DocumentSearchResult] = Field(default_factory=list)
    page: int
    page_size: int
    total: int
