"""Schemas for income/expense lines, financial summary, and tax calculation."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.core.api_types import ApiDateTime, ApiDecimal
from app.core.schemas.validation import NonEmptyUpdateMixin

# ── Income ────────────────────────────────────────────────────────────────────


class IncomeLineCreateRequest(BaseModel):
    source_type: IncomeSourceType  # enum — לא str חופשי
    amount: ApiDecimal = Field(ge=0)
    description: str | None = None


class IncomeLineUpdateRequest(NonEmptyUpdateMixin):
    source_type: IncomeSourceType | None = None
    amount: ApiDecimal | None = Field(None, ge=0)
    description: str | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> IncomeLineUpdateRequest:
        for field in ("source_type", "amount"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class IncomeLineResponse(BaseModel):
    id: int
    annual_report_id: int
    source_type: IncomeSourceType
    amount: ApiDecimal
    description: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


# ── Expenses ──────────────────────────────────────────────────────────────────


class ExpenseLineCreateRequest(BaseModel):
    category: ExpenseCategoryType  # enum — לא str חופשי
    amount: ApiDecimal = Field(gt=0)
    description: str | None = None
    recognition_rate: ApiDecimal | None = Field(None, ge=0, le=1)
    external_document_reference: str | None = Field(
        None,
        validation_alias=AliasChoices("external_document_reference", "supporting_document_ref"),
    )
    supporting_document_id: int | None = None

    model_config = {"populate_by_name": True}


class ExpenseLineUpdateRequest(NonEmptyUpdateMixin):
    category: ExpenseCategoryType | None = None
    amount: ApiDecimal | None = Field(None, gt=0)
    description: str | None = None
    recognition_rate: ApiDecimal | None = Field(None, ge=0, le=1)
    external_document_reference: str | None = None
    supporting_document_id: int | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> ExpenseLineUpdateRequest:
        # category/amount/recognition_rate are non-nullable columns
        # (recognition_rate has a DB default of 1.00, so null is not "clear").
        for field in ("category", "amount", "recognition_rate"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class ExpenseLineResponse(BaseModel):
    id: int
    annual_report_id: int
    category: ExpenseCategoryType
    amount: ApiDecimal
    recognition_rate: ApiDecimal
    recognized_amount: ApiDecimal = Decimal("0")
    external_document_reference: str | None = None
    supporting_document_id: int | None = None
    supporting_document_filename: str | None = None
    description: str | None = None
    created_at: ApiDateTime
    updated_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        instance = super().model_validate(obj, *args, **kwargs)
        if hasattr(obj, "supporting_document") and obj.supporting_document is not None:
            key = obj.supporting_document.storage_key or ""
            object.__setattr__(instance, "supporting_document_filename", key.split("/")[-1])
        return instance

    def model_post_init(self, _context: object) -> None:
        object.__setattr__(
            self,
            "recognized_amount",
            (self.amount * self.recognition_rate).quantize(Decimal("0.01")),
        )


# ── Financial summary ─────────────────────────────────────────────────────────


class FinancialSummaryResponse(BaseModel):
    annual_report_id: int
    total_income: ApiDecimal
    gross_expenses: ApiDecimal
    recognized_expenses: ApiDecimal
    taxable_income: ApiDecimal
    income_lines: list[IncomeLineResponse] = []
    expense_lines: list[ExpenseLineResponse] = []


# ── Tax calculation ───────────────────────────────────────────────────────────


class BracketBreakdownItem(BaseModel):
    rate: ApiDecimal
    from_amount: ApiDecimal
    to_amount: ApiDecimal | None = None
    taxable_in_bracket: ApiDecimal
    tax_in_bracket: ApiDecimal


class NationalInsuranceResponse(BaseModel):
    base_amount: ApiDecimal
    high_amount: ApiDecimal
    total: ApiDecimal


class TaxCalculationResponse(BaseModel):
    taxable_income: ApiDecimal
    pension_deduction: ApiDecimal
    tax_before_credits: ApiDecimal
    credit_points_value: ApiDecimal
    donation_credit: ApiDecimal
    other_credits: ApiDecimal
    tax_after_credits: ApiDecimal
    net_profit: ApiDecimal
    effective_rate: ApiDecimal
    national_insurance: NationalInsuranceResponse
    brackets: list[BracketBreakdownItem]
    total_liability: ApiDecimal
    total_credit_points: ApiDecimal
    # Advances already paid for this tax year, and what remains after them. Both
    # come from the SQL aggregate over PAID rows; nothing recomputes either.
    advances_paid: ApiDecimal
    final_balance: ApiDecimal


# ── Advances summary ──────────────────────────────────────────────────────────


class AdvancesSummary(BaseModel):
    total_advances_paid: ApiDecimal
    advances_count: int
    final_balance: ApiDecimal
    balance_type: Literal["due", "refund", "zero"]


# ── Readiness check ───────────────────────────────────────────────────────────


class ReadinessCheckResponse(BaseModel):
    annual_report_id: int
    is_ready: bool
    issues: list[str]
    completion_pct: float  # 0.0–100.0, rounded to 1 decimal


# ── Tax calculation save ──────────────────────────────────────────────────────


class TaxCalculationSaveRequest(BaseModel):
    tax_due: ApiDecimal | None = None
    refund_due: ApiDecimal | None = None


class TaxCalculationSaveResponse(BaseModel):
    annual_report_id: int
    tax_due: ApiDecimal | None = None
    refund_due: ApiDecimal | None = None
    saved_at: ApiDateTime


# ── Tax preview (pre-creation) ────────────────────────────────────────────────


class TaxPreviewRequest(BaseModel):
    tax_year: int
    gross_income: ApiDecimal = Field(ge=0)
    expenses: ApiDecimal = Field(ge=0)
    advances_paid: ApiDecimal = Field(ge=0)
    credit_points: ApiDecimal = Field(ge=0)


class TaxPreviewResponse(BaseModel):
    net_profit: ApiDecimal
    estimated_tax: ApiDecimal
    balance: ApiDecimal


# ── VAT auto-populate ─────────────────────────────────────────────────────────


class VatAutoPopulateSkippedItem(BaseModel):
    item_type: Literal["income", "expense"]
    source: str
    amount: ApiDecimal
    reason: Literal["zero_total", "negative_total", "negative_source_contribution"]
    annual_category: ExpenseCategoryType | None = None


class VatAutoPopulateExpenseBreakdownItem(BaseModel):
    annual_category: ExpenseCategoryType
    amount: ApiDecimal
    source_vat_categories: dict[str, ApiDecimal]


class VatAutoPopulateResponse(BaseModel):
    annual_report_id: int
    income_lines_created: int
    expense_lines_created: int
    income_total: ApiDecimal
    expense_total: ApiDecimal
    lines_deleted: int = 0
    skipped_items: list[VatAutoPopulateSkippedItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    expense_breakdown: list[VatAutoPopulateExpenseBreakdownItem] = Field(default_factory=list)
