"""Endpoint for saving computed tax calculation results to an annual report."""

from fastapi import APIRouter, Depends

from app.annual_reports.schemas.annual_report_financials import (
    TaxCalculationSaveRequest,
    TaxCalculationSaveResponse,
)
from app.annual_reports.services.tax_service import (
    AnnualReportTaxService,
)
from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)


@router.post(
    "/{report_id}/tax-calculation/save",
    response_model=TaxCalculationSaveResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def save_tax_calculation(
    report_id: int,
    body: TaxCalculationSaveRequest,
    db: DBSession,
    user: CurrentUser,
):
    """שמירת חוב מס / החזר מס מחושב על הדוח השנתי.

    יש לקרוא ל-GET /tax-calculation תחילה, ולאחר מכן לשמור את התוצאה.
    לא ניתן לשמור גם tax_due וגם refund_due בו-זמנית.
    """
    svc = AnnualReportTaxService(db)
    return svc.save_tax_calculation(report_id, body.tax_due, body.refund_due)


__all__ = ["router"]
