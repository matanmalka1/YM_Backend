"""Endpoint for listing charges linked to an annual report."""

from fastapi import APIRouter, Depends, Query

from app.annual_reports.services.annual_report_charge_service import (
    AnnualReportChargeService,
)
from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("/{report_id}/charges", responses=not_found_response(description="הדוח המבוקש לא נמצא"))
def list_report_charges(
    report_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """רשימת חיובים המקושרים לדוח שנתי זה (מידע בלבד)."""
    svc = AnnualReportChargeService(db)
    charges, total = svc.list_charges(report_id, page=page, page_size=page_size)
    return {"items": charges, "page": page, "page_size": page_size, "total": total}


__all__ = ["router"]
