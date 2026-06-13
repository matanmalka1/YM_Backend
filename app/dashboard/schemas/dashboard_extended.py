from datetime import date

from pydantic import BaseModel, Field

from app.core.api_types import ApiDecimal


class AttentionBoardItem(BaseModel):
    id: str = Field(
        pattern=r"^\w+:\d+$",
        description=(
            "Stable composite attention key in the form '{source_type}:{source_id}', "
            "for example 'charge:123'."
        ),
    )
    source_type: str
    source_id: int
    title: str
    client_name: str | None = None
    due_date: date | None = None
    days_delta: int = 0
    reason: str | None = None
    amount: ApiDecimal | None = None
    urgency: str
    href: str


class AttentionResponse(BaseModel):
    items: list[AttentionBoardItem] = Field(default_factory=list)
    total: int = 0


class VatDashboardPeriodStat(BaseModel):
    period: str
    period_label: str
    status_label: str = ""
    submitted: int = 0
    required: int = 0
    pending: int = 0
    completion_percent: int = 0


class AdvancePaymentDashboardStats(BaseModel):
    monthly: VatDashboardPeriodStat
    bimonthly: VatDashboardPeriodStat


class VatDashboardStats(BaseModel):
    monthly: VatDashboardPeriodStat
    bimonthly: VatDashboardPeriodStat
    advance_payments: AdvancePaymentDashboardStats


class RecentActivityItem(BaseModel):
    id: int
    date: str
    time: str
    label: str
    client_name: str
    href: str
    activity_type: str


class DashboardOverviewResponse(BaseModel):
    """Dashboard overview — advisor gets full data, secretary gets operational subset."""

    is_empty: bool
    open_charges_count: int = 0
    open_charges_amount_ils: str | None = None
    vat_stats: VatDashboardStats
    attention: AttentionResponse = Field(default_factory=AttentionResponse)
    recent_activity: list[RecentActivityItem] = Field(default_factory=list)
