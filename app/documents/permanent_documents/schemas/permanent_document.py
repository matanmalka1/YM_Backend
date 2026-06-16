from pydantic import BaseModel, model_validator

from app.core.api_types import ApiDateTime, NonBlankStr, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    DocumentStatus,
    PermanentDocumentType,
)


class PermanentDocumentResponse(BaseModel):
    id: int
    client_record_id: int
    client_name: str | None = None
    business_id: int | None = None  # nullable — CLIENT scope
    scope: DocumentScope
    document_type: PermanentDocumentType
    storage_key: str
    original_filename: str | None = None
    file_size_bytes: int | None = None
    mime_type: str | None = None
    tax_year: int | None = None
    is_present: bool
    is_deleted: bool
    status: DocumentStatus
    version: int
    superseded_by: int | None = None
    annual_report_id: int | None = None
    binder_id: int | None = None
    uploaded_by: int
    uploaded_at: ApiDateTime
    approved_by: int | None = None
    approved_at: ApiDateTime | None = None
    rejected_by: int | None = None
    rejected_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


class PermanentDocumentUpdateRequest(NonEmptyUpdateMixin):
    document_type: PermanentDocumentType | None = None
    original_filename: NonBlankStr | None = None
    tax_year: int | None = None

    @model_validator(mode="after")
    def _reject_null_document_type(self):
        if "document_type" in self.model_fields_set and self.document_type is None:
            raise ValueError("document_type לא יכול להיות null")
        return self


class PermanentDocumentListResponse(PaginatedResponse[PermanentDocumentResponse]):
    pass


class DocumentVersionsResponse(BaseModel):
    items: list[PermanentDocumentResponse]
    limit: int | None = None
    has_more: bool = False


class OperationalSignalsResponse(BaseModel):
    client_record_id: int
    missing_documents: list[PermanentDocumentType]


class DocumentDownloadUrlResponse(BaseModel):
    url: str
