"""Routes: VAT work item status transitions."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import User, UserRole
from app.vat.api.serializers import serialize_work_item
from app.vat.schemas.vat_report import (
    SendBackForCorrectionRequest,
    VatWorkItemResponse,
)
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.post(
    "/work-items/{item_id}/ready-for-review",
    response_model=VatWorkItemResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def mark_ready_for_review(
    item_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Mark data entry complete: DATA_ENTRY_IN_PROGRESS → READY_FOR_REVIEW.

    Accessible by: secretary, advisor.
    """
    service = VatReportService(db)
    item = service.mark_ready_for_review(
        item_id=item_id,
        performed_by=current_user.id,
    )
    return serialize_work_item(service, item.id, current_user.role)


@router.post(
    "/work-items/{item_id}/send-back",
    response_model=VatWorkItemResponse,
)
def send_back_for_correction(
    item_id: int,
    request: SendBackForCorrectionRequest,
    db: DBSession,
    current_user: Annotated[User, Depends(require_role(UserRole.ADVISOR))],
):
    """
    Advisor sends work item back for correction.
    READY_FOR_REVIEW → DATA_ENTRY_IN_PROGRESS.
    """
    service = VatReportService(db)
    item = service.send_back_for_correction(
        item_id=item_id,
        performed_by=current_user.id,
        correction_note=request.correction_note,
    )
    return serialize_work_item(service, item.id, current_user.role)
