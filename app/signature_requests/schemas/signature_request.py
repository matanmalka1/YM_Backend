from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field, computed_field

from app.core.api_types import ApiDateTime, PaginatedResponse
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)

# ── Audit event ───────────────────────────────────────────────────────────────


class SignatureAuditEventResponse(BaseModel):
    id: int
    event_type: str  # String במודל — לא enum, מרחיב בחופשיות
    actor_type: str  # String במודל — לא enum
    actor_id: int | None = None
    actor_name: str | None = None
    ip_address: str | None = None
    notes: str | None = None
    occurred_at: ApiDateTime

    model_config = {"from_attributes": True}


# ── Core response ─────────────────────────────────────────────────────────────


class SignatureRequestResponse(BaseModel):
    id: int
    client_record_id: int  # PRIMARY anchor — always present
    office_client_number: int | None = None
    business_id: int | None = None  # OPTIONAL context
    business_name: str | None = None  # enriched by route layer when business_id set
    created_by: int
    request_type: SignatureRequestType
    title: str
    description: str | None = None
    signer_name: str
    signer_email: str | None = None
    signer_phone: str | None = None
    status: SignatureRequestStatus
    content_hash: str | None = None
    storage_key: str | None = None
    annual_report_id: int | None = None
    document_id: int | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None
    sent_at: ApiDateTime | None = None
    expires_at: ApiDateTime | None = None
    signed_at: ApiDateTime | None = None
    declined_at: ApiDateTime | None = None
    canceled_at: ApiDateTime | None = None
    canceled_by: int | None = None
    # signer_ip_address intentionally excluded — PII, available only in audit trail
    decline_reason: str | None = None
    signed_document_key: str | None = None

    model_config = {"from_attributes": True}


class SignatureRequestListResponse(PaginatedResponse[SignatureRequestResponse]):
    pass


class SignatureRequestWithAuditResponse(SignatureRequestResponse):
    audit_trail: list[SignatureAuditEventResponse] = []


# ── Advisor create request ────────────────────────────────────────────────────


class SignatureRequestCreateRequest(BaseModel):
    client_record_id: int = Field(gt=0)  # PRIMARY anchor — always required
    business_id: int | None = Field(None, gt=0)  # OPTIONAL; validated server-side for ownership
    request_type: SignatureRequestType
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(None, max_length=2000)
    signer_name: str = Field(min_length=2, max_length=100)
    signer_email: EmailStr | None = None
    signer_phone: str | None = None
    annual_report_id: int | None = Field(None, gt=0)
    document_id: int | None = Field(None, gt=0)
    content_to_hash: str | None = None  # service computes SHA-256
    expiry_days: int = Field(14, ge=1, le=90)


class SignatureRequestCreatedResponse(SignatureRequestResponse):
    """Returned once on creation with the signing link token."""

    signing_token: str
    signing_url_hint: str


class CancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


# ── Signer-facing (public, no JWT) ───────────────────────────────────────────


class SignerViewResponse(BaseModel):
    """Minimal — no internal IDs or financial data."""

    request_id: int
    title: str
    description: str | None = None
    signer_name: str
    status: SignatureRequestStatus
    content_hash: str | None = None
    expires_at: ApiDateTime | None = None

    @computed_field
    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.now(UTC)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
        return exp < now


class SignerDeclineRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)
