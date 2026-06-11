"""Routes: work item creation and material intake."""

from fastapi import APIRouter, Depends, status

from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole
from app.vat.api.serializers import serialize_work_item
from app.vat.schemas.vat_report import (
    VatWorkItemCreateRequest,
    VatWorkItemResponse,
)
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.post(
    "/work-items",
    response_model=VatWorkItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def create_work_item(
    request: VatWorkItemCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Create a VAT work item for a business / period.

    Accessible by: receptionist, secretary, advisor.
    """
    service = VatReportService(db)
    item = service.create_work_item(
        client_record_id=request.client_record_id,
        period=request.period,
        created_by=current_user.id,
        assigned_to=request.assigned_to,
        mark_pending=request.mark_pending,
        pending_materials_note=request.pending_materials_note,
    )
    return serialize_work_item(service, item.id, current_user.role)


@router.post(
    "/work-items/{item_id}/materials-complete",
    response_model=VatWorkItemResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def mark_materials_complete(
    item_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Mark materials as complete: PENDING_MATERIALS → MATERIAL_RECEIVED.

    Accessible by: receptionist, secretary, advisor.
    """
    service = VatReportService(db)
    item = service.mark_materials_complete(
        item_id=item_id,
        performed_by=current_user.id,
    )
    return serialize_work_item(service, item.id, current_user.role)
