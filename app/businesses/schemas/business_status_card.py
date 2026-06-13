from pydantic import BaseModel

from app.core.api_types import ApiDateTime, ApiDecimal


class VatSummaryCard(BaseModel):
    net_vat_total: ApiDecimal
    periods_filed: int
    periods_total: int
    latest_period: str | None = None


class AnnualReportCard(BaseModel):
    status: str | None = None
    form_type: str | None = None
    filing_deadline: ApiDateTime | None = None
    refund_due: ApiDecimal | None = None
    tax_due: ApiDecimal | None = None


class ChargesCard(BaseModel):
    total_outstanding: ApiDecimal
    unpaid_count: int


class AdvancePaymentsCard(BaseModel):
    total_paid: ApiDecimal
    count: int


class BindersCard(BaseModel):
    active_count: int
    in_office_count: int


class DocumentsCard(BaseModel):
    total_count: int
    present_count: int


class ClientStatusCardResponse(BaseModel):
    client_id: int
    year: int
    client_vat: VatSummaryCard
    annual_report: AnnualReportCard
    charges: ChargesCard
    advance_payments: AdvancePaymentsCard
    binders: BindersCard
    documents: DocumentsCard
