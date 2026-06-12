"""Routes: advisor review and filing (advisor-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.users.api.deps import DBSession, require_role
from app.users.models.user import User, UserRole
from app.vat.api.responses import VAT_WORK_ITEM_TRANSITION_RESPONSES
from app.vat.api.serializers import serialize_work_item
from app.vat.schemas.vat_report import FileVatReturnRequest, VatWorkItemResponse
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.post(
    "/work-items/{item_id}/file",
    response_model=VatWorkItemResponse,
    responses=VAT_WORK_ITEM_TRANSITION_RESPONSES,
)
def file_vat_return(
    item_id: int,
    request: FileVatReturnRequest,
    db: DBSession,
    current_user: Annotated[User, Depends(require_role(UserRole.ADVISOR))],
):
    """
    Confirm and file the VAT return.  Locks the period.

    Advisor only.
    Override amount requires written justification.
    """
    service = VatReportService(db)
    item = service.file_vat_return(
        item_id=item_id,
        filed_by=current_user.id,
        submission_method=request.submission_method,
        override_amount=float(request.override_amount)
        if request.override_amount is not None
        else None,
        override_justification=request.override_justification,
        submission_reference=request.submission_reference,
        is_amendment=request.is_amendment,
        amends_item_id=request.amends_item_id,
    )
    return serialize_work_item(service, item.id, current_user.role)
