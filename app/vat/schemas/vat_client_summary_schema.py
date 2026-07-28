from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.common.enums import ObligationStatus
from app.core.api_types import ApiDateTime, ApiDecimal


class VatPeriodRow(BaseModel):
    work_item_id: int = 0
    period: str
    period_type: str | None = None
    status: ObligationStatus
    total_output_vat: ApiDecimal
    total_input_vat: ApiDecimal
    net_vat: ApiDecimal
    total_output_net: ApiDecimal = Decimal("0")
    total_input_net: ApiDecimal = Decimal("0")
    final_vat_amount: ApiDecimal | None = None
    filed_at: ApiDateTime | None = None
    submission_deadline: date | None = None
    statutory_deadline: date | None = None
    extended_deadline: date | None = None
    days_until_deadline: int | None = None
    is_overdue: bool | None = None

    model_config = {"from_attributes": True}


class VatAnnualSummary(BaseModel):
    year: int
    total_output_vat: ApiDecimal
    total_input_vat: ApiDecimal
    net_vat: ApiDecimal
    periods_count: int
    filed_count: int


class VatClientSummaryResponse(BaseModel):
    client_record_id: int
    periods: list[VatPeriodRow]
    annual: list[VatAnnualSummary]
