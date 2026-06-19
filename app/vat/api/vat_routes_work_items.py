"""Routes: VAT work item metadata mutations."""

from fastapi import APIRouter, Depends, status

from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole
from app.vat.api.vat_responses import VAT_WORK_ITEM_MUTATION_RESPONSES
from app.vat.api.vat_serializers import serialize_work_item
from app.vat.schemas.vat_report import (
    VatWorkItemResponse,
    VatWorkItemUpdateRequest,
)
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.patch(
    "/work-items/{item_id}",
    response_model=VatWorkItemResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=VAT_WORK_ITEM_MUTATION_RESPONSES,
)
def update_work_item_metadata(
    item_id: PathId,
    request: VatWorkItemUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    service = VatReportService(db)
    item = service.update_work_item_metadata(
        item_id=item_id,
        performed_by=current_user.id,
        patch=request.model_dump(exclude_unset=True),
    )
    return serialize_work_item(service, item.id, current_user.role)


@router.delete(
    "/work-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=VAT_WORK_ITEM_MUTATION_RESPONSES,
)
def delete_work_item(
    item_id: PathId,
    db: DBSession,
    current_user: CurrentUser,
):
    service = VatReportService(db)
    service.soft_delete_work_item(
        item_id=item_id,
        deleted_by=current_user.id,
    )
