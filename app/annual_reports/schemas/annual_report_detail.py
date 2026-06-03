from pydantic import BaseModel, Field

from app.core.api_types import ApiDateTime, ApiDecimal

# ── Detail (ניכויים ואישורים) ─────────────────────────────────────────────────


class ReportDetailResponse(BaseModel):
    """AnnualReportDetail — ניכויים, אישור לקוח, הערות."""

    report_id: int
    pension_contribution: ApiDecimal | None = None
    donation_amount: ApiDecimal | None = None
    other_credits: ApiDecimal | None = None
    tax_refund_amount: ApiDecimal | None = None
    tax_due_amount: ApiDecimal | None = None
    client_approved_at: ApiDateTime | None = None
    internal_notes: str | None = None
    amendment_reason: str | None = None
    created_at: ApiDateTime | None = None
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


class AnnualReportDetailUpdateRequest(BaseModel):
    pension_contribution: ApiDecimal | None = Field(None, ge=0)
    donation_amount: ApiDecimal | None = Field(None, ge=0)
    other_credits: ApiDecimal | None = Field(None, ge=0)
    client_approved_at: ApiDateTime | None = None
    internal_notes: str | None = None
    amendment_reason: str | None = None
