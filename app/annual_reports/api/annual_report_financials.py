"""Endpoints for income lines, expense lines, financial summary, readiness, and VAT import."""

from fastapi import APIRouter, Depends, Query, status

from app.annual_reports.schemas.annual_report_financials import (
    AdvancesSummary,
    ExpenseLineCreateRequest,
    ExpenseLineResponse,
    ExpenseLineUpdateRequest,
    FinancialSummaryResponse,
    IncomeLineCreateRequest,
    IncomeLineResponse,
    IncomeLineUpdateRequest,
    ReadinessCheckResponse,
    TaxCalculationResponse,
    TaxPreviewRequest,
    TaxPreviewResponse,
    VatAutoPopulateResponse,
)
from app.annual_reports.services.advances_summary_service import (
    AnnualReportAdvancesSummaryService,
)
from app.annual_reports.services.financial_service import AnnualReportFinancialService
from app.annual_reports.services.tax_engine import calculate_tax
from app.annual_reports.services.vat_import_service import VatImportService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


# ── Tax preview (pre-creation, no report_id needed) ──────────────────────────


@router.post("/tax-preview", response_model=TaxPreviewResponse)
def get_tax_preview(body: TaxPreviewRequest, _user: CurrentUser):
    """הערכת מס מקדימה לפני יצירת דוח שנתי."""
    net_profit = float(body.gross_income) - float(body.expenses)
    result = calculate_tax(
        taxable_income=max(net_profit, 0.0),
        tax_year=body.tax_year,
        credit_points=body.credit_points,
    )
    balance = result.tax_after_credits - float(body.advances_paid)
    return TaxPreviewResponse(
        net_profit=round(net_profit, 2),
        estimated_tax=result.tax_after_credits,
        balance=round(balance, 2),
    )


# ── Financial summary ─────────────────────────────────────────────────────────


@router.get("/{report_id}/financials", response_model=FinancialSummaryResponse)
def get_financial_summary(report_id: int, db: DBSession, user: CurrentUser):
    """Income + expense lines and taxable income calculation."""
    svc = AnnualReportFinancialService(db)
    return svc.get_financial_summary(report_id)


# ── Tax calculation ───────────────────────────────────────────────────────────


@router.get("/{report_id}/tax-calculation", response_model=TaxCalculationResponse)
def get_tax_calculation(report_id: int, db: DBSession, user: CurrentUser):
    """Israeli 2024 income tax calculation for this report."""
    svc = AnnualReportFinancialService(db)
    return svc.get_tax_calculation(report_id)


# ── Advances summary ──────────────────────────────────────────────────────────


@router.get("/{report_id}/advances-summary", response_model=AdvancesSummary)
def get_advances_summary(report_id: int, db: DBSession, user: CurrentUser):
    """Advance payments summary and final tax balance for this report."""
    svc = AnnualReportAdvancesSummaryService(db)
    return svc.get_advances_summary(report_id)


# ── Readiness check ───────────────────────────────────────────────────────────


@router.get("/{report_id}/readiness", response_model=ReadinessCheckResponse)
def get_readiness_check(report_id: int, db: DBSession, user: CurrentUser):
    """Return list of issues blocking this report from being filed."""
    svc = AnnualReportFinancialService(db)
    return svc.get_readiness_check(report_id)


# ── Income lines ──────────────────────────────────────────────────────────────


@router.post(
    "/{report_id}/income",
    response_model=IncomeLineResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_income_line(
    report_id: int, body: IncomeLineCreateRequest, db: DBSession, user: CurrentUser
):
    svc = AnnualReportFinancialService(db)
    return svc.add_income(
        report_id, body.source_type, body.amount, body.description, actor_id=user.id
    )


@router.patch(
    "/{report_id}/income/{line_id}",
    response_model=IncomeLineResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def update_income_line(
    report_id: int,
    line_id: int,
    body: IncomeLineUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportFinancialService(db)
    return svc.update_income(
        report_id, line_id, actor_id=user.id, **body.model_dump(exclude_none=True)
    )


@router.delete(
    "/{report_id}/income/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def delete_income_line(report_id: int, line_id: int, db: DBSession, user: CurrentUser):
    svc = AnnualReportFinancialService(db)
    svc.delete_income(report_id, line_id, actor_id=user.id)


# ── Expense lines ─────────────────────────────────────────────────────────────


@router.post(
    "/{report_id}/expenses",
    response_model=ExpenseLineResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_expense_line(
    report_id: int, body: ExpenseLineCreateRequest, db: DBSession, user: CurrentUser
):
    svc = AnnualReportFinancialService(db)
    return svc.add_expense(
        report_id,
        body.category,
        body.amount,
        body.description,
        body.recognition_rate,
        body.external_document_reference,
        body.supporting_document_id,
        actor_id=user.id,
    )


@router.patch(
    "/{report_id}/expenses/{line_id}",
    response_model=ExpenseLineResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def update_expense_line(
    report_id: int,
    line_id: int,
    body: ExpenseLineUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportFinancialService(db)
    return svc.update_expense(
        report_id, line_id, actor_id=user.id, **body.model_dump(exclude_none=True)
    )


@router.delete(
    "/{report_id}/expenses/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def delete_expense_line(report_id: int, line_id: int, db: DBSession, user: CurrentUser):
    svc = AnnualReportFinancialService(db)
    svc.delete_expense(report_id, line_id, actor_id=user.id)


# ── VAT auto-populate ─────────────────────────────────────────────────────────


@router.post(
    "/{report_id}/auto-populate",
    response_model=VatAutoPopulateResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def auto_populate_from_vat(
    report_id: int,
    db: DBSession,
    user: CurrentUser,
    force: bool = Query(False, description="מחק שורות קיימות ומלא מחדש"),
):
    """מילוי אוטומטי של שורות הכנסה/הוצאה מנתוני מע\"מ של העסק לשנת המס."""
    svc = VatImportService(db)
    result = svc.auto_populate(report_id, force=force, actor_id=user.id)
    return VatAutoPopulateResponse(**result)
