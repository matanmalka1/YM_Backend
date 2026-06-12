from fastapi import APIRouter, Depends, Query

from app.binders.schemas.binder_extended import (
    BinderDetailResponse,
    BinderListResponseExtended,
)
from app.binders.services.binder_operations_service import BinderOperationsService
from app.clients.services.client_service import get_client_or_raise
from app.core.openapi_responses import not_found_response
from app.users.api.deps import DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients",
    tags=["clients-binders"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{client_record_id}/binders",
    response_model=BinderListResponseExtended,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_client_binders(
    client_record_id: int,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all binders for a specific client."""
    get_client_or_raise(db, client_record_id)

    service = BinderOperationsService(db)
    items, total = service.get_client_binders(
        client_record_id=client_record_id,
        page=page,
        page_size=page_size,
    )

    enriched = [BinderDetailResponse(**service.enrich_binder(b)) for b in items]

    return BinderListResponseExtended(
        items=enriched,
        page=page,
        page_size=page_size,
        total=total,
    )
