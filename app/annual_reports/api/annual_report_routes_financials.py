"""Endpoints for income lines, expense lines, financial summary, readiness, and VAT import."""

from fastapi import APIRouter, Depends, Query, status

from app.annual_reports.api.annual_report_responses import (
    REPORT_LINE_WRITE_RESPONSES,
    REPORT_UPDATE_RESPONSES,
)
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
from app.annual_reports.services.annual_report_advances_summary_service import (
    AnnualReportAdvancesSummaryService,
)
from app.annual_reports.services.annual_report_financial_line_service import AnnualReportFinancialLineService
from app.annual_reports.services.annual_report_financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.annual_report_readiness_service import AnnualReportReadinessService
from app.annual_reports.services.annual_report_tax_engine import calculate_tax
from app.annual_reports.services.annual_report_tax_service import (
    AnnualReportTaxService,
)
from app.annual_reports.services.annual_report_vat_import_service import VatImportService
from app.core.openapi_responses import not_found_response
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
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


@router.get(
    "/{report_id}/financials",
    response_model=FinancialSummaryResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_financial_summary(report_id: PathId, db: DBSession, user: CurrentUser):
    """Income + expense lines and taxable income calculation."""
    svc = AnnualReportFinancialSummaryService(db)
    return svc.get_financial_summary(report_id)


# ── Tax calculation ───────────────────────────────────────────────────────────


@router.get(
    "/{report_id}/tax-calculation",
    response_model=TaxCalculationResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_tax_calculation(report_id: PathId, db: DBSession, user: CurrentUser):
    """Israeli 2024 income tax calculation for this report."""
    svc = AnnualReportTaxService(db)
    return svc.get_tax_calculation(report_id)


# ── Advances summary ──────────────────────────────────────────────────────────


@router.get(
    "/{report_id}/advances-summary",
    response_model=AdvancesSummary,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_advances_summary(report_id: PathId, db: DBSession, user: CurrentUser):
    """Advance payments summary and final tax balance for this report."""
    svc = AnnualReportAdvancesSummaryService(db)
    return svc.get_advances_summary(report_id)


# ── Readiness check ───────────────────────────────────────────────────────────


@router.get(
    "/{report_id}/readiness",
    response_model=ReadinessCheckResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_readiness_check(report_id: PathId, db: DBSession, user: CurrentUser):
    """Return list of issues blocking this report from being filed."""
    svc = AnnualReportReadinessService(db)
    return svc.get_readiness_check(report_id)


# ── Income lines ──────────────────────────────────────────────────────────────


@router.post(
    "/{report_id}/income",
    response_model=IncomeLineResponse,
    status_code=status.HTTP_201_CREATED,
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def add_income_line(
    report_id: PathId, body: IncomeLineCreateRequest, db: DBSession, user: CurrentUser
):
    svc = AnnualReportFinancialLineService(db)
    return svc.add_income(
        report_id, body.source_type, body.amount, body.description, actor_id=user.id
    )


@router.patch(
    "/{report_id}/income/{line_id}",
    response_model=IncomeLineResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def update_income_line(
    report_id: PathId,
    line_id: PathId,
    body: IncomeLineUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportFinancialLineService(db)
    return svc.update_income(
        report_id, line_id, actor_id=user.id, **body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{report_id}/income/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def delete_income_line(report_id: PathId, line_id: PathId, db: DBSession, user: CurrentUser):
    svc = AnnualReportFinancialLineService(db)
    svc.delete_income(report_id, line_id, actor_id=user.id)


# ── Expense lines ─────────────────────────────────────────────────────────────


@router.post(
    "/{report_id}/expenses",
    response_model=ExpenseLineResponse,
    status_code=status.HTTP_201_CREATED,
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def add_expense_line(
    report_id: PathId, body: ExpenseLineCreateRequest, db: DBSession, user: CurrentUser
):
    svc = AnnualReportFinancialLineService(db)
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
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def update_expense_line(
    report_id: PathId,
    line_id: PathId,
    body: ExpenseLineUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportFinancialLineService(db)
    return svc.update_expense(
        report_id, line_id, actor_id=user.id, **body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{report_id}/expenses/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def delete_expense_line(report_id: PathId, line_id: PathId, db: DBSession, user: CurrentUser):
    svc = AnnualReportFinancialLineService(db)
    svc.delete_expense(report_id, line_id, actor_id=user.id)


# ── VAT auto-populate ─────────────────────────────────────────────────────────


@router.post(
    "/{report_id}/auto-populate",
    response_model=VatAutoPopulateResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_UPDATE_RESPONSES,
)
def auto_populate_from_vat(
    report_id: PathId,
    db: DBSession,
    user: CurrentUser,
    force: bool = Query(False, description="מחק שורות קיימות ומלא מחדש"),
):
    """מילוי אוטומטי של שורות הכנסה/הוצאה מנתוני מע\"מ של העסק לשנת המס."""
    svc = VatImportService(db)
    result = svc.auto_populate(report_id, force=force, actor_id=user.id)
    return VatAutoPopulateResponse(**result)
