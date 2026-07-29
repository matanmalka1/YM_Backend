"""Routes: advisor review and filing (advisor-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.openapi_responses import not_found_response
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import User, UserRole
from app.vat.api.vat_responses import (
    VAT_WORK_ITEM_AMEND_RESPONSES,
    VAT_WORK_ITEM_TRANSITION_RESPONSES,
)
from app.vat.api.vat_serializers import serialize_work_item
from app.vat.schemas.vat_report import (
    FileVatReturnRequest,
    VatClosingReadinessResponse,
    VatWorkItemResponse,
)
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.get(
    "/work-items/{item_id}/readiness",
    response_model=VatClosingReadinessResponse,
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def get_closing_readiness(item_id: PathId, db: DBSession, user: CurrentUser):
    """Return list of issues blocking this VAT period from being filed."""
    service = VatReportService(db)
    return service.get_closing_readiness(item_id)


@router.post(
    "/work-items/{item_id}/file",
    response_model=VatWorkItemResponse,
    responses=VAT_WORK_ITEM_TRANSITION_RESPONSES,
)
def file_vat_return(
    item_id: PathId,
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
        closed_by=current_user.id,
        submission_method=request.submission_method,
        override_amount=float(request.override_amount)
        if request.override_amount is not None
        else None,
        override_justification=request.override_justification,
        submission_reference=request.submission_reference,
        actor_display_name=current_user.full_name,
    )
    return serialize_work_item(service, item.id, current_user.role)


@router.post(
    "/work-items/{item_id}/amend",
    response_model=VatWorkItemResponse,
    status_code=201,
    responses=VAT_WORK_ITEM_AMEND_RESPONSES,
)
def create_amendment(
    item_id: PathId,
    db: DBSession,
    current_user: Annotated[User, Depends(require_role(UserRole.ADVISOR))],
):
    """
    Open a correction of a closed VAT period as a new record (D-10, D-21).

    Advisor only. The original stays closed and keeps its figures; the new
    record is a full copy, invoices included, opening at "in progress".
    Returns the amendment, not the original.
    """
    service = VatReportService(db)
    amendment = service.create_amendment(
        item_id=item_id,
        actor_id=current_user.id,
        actor_display_name=current_user.full_name,
    )
    return serialize_work_item(service, amendment.id, current_user.role)


@router.get(
    "/work-items/{item_id}/chain",
    response_model=list[VatWorkItemResponse],
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def list_amendment_chain(item_id: PathId, db: DBSession, user: CurrentUser):
    """Every record for this period, oldest first — the correction history.

    The one read that deliberately includes superseded records: the corrected
    ones are the point. Every other list shows the chain as a single row (D-12).
    """
    service = VatReportService(db)
    return [
        serialize_work_item(service, record.id, user.role)
        for record in service.list_chain(item_id=item_id)
    ]
