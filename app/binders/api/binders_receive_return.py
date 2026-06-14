from fastapi import APIRouter, Depends, status

from app.binders.api.responses import (
    BINDER_ACTION_RESPONSES,
    BINDER_HANDOVER_BULK_RESPONSES,
    BINDER_READY_BULK_RESPONSES,
    BINDER_RECEIVE_RESPONSES,
)
from app.binders.repositories.binder_handover_repository import BinderHandoverRepository
from app.binders.schemas.binder import (
    BinderHandoverRequest,
    BinderHandoverResponse,
    BinderHandoverToClientRequest,
    BinderIntakeResponse,
    BinderMarkReadyForHandoverBulkRequest,
    BinderReadyForHandoverResponse,
    BinderReceiveRequest,
    BinderReceiveResult,
    BinderResponse,
)
from app.binders.services.binder_handover_service import BinderHandoverService
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.binders.services.binder_list_service import BinderListService
from app.binders.services.binder_service import BinderService
from app.core.path_params import PathId
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/binders",
    tags=["binders"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


def fetch_client_and_build_response(binder, db: DBSession) -> BinderResponse:
    service = BinderListService(db)
    enriched = service.get_binder_with_client_name(binder.id)
    return enriched or service.build_binder_response(binder)


@router.post(
    "/receive",
    response_model=BinderReceiveResult,
    status_code=status.HTTP_201_CREATED,
    responses=BINDER_RECEIVE_RESPONSES,
)
def receive_binder(request: BinderReceiveRequest, db: DBSession, user: CurrentUser):
    service = BinderService(db)
    materials = [m.model_dump() for m in request.materials] if request.materials else []
    binder, intake, is_new_binder = service.receive_binder(
        client_record_id=request.client_record_id,
        open_new_binder=request.open_new_binder,
        received_at=request.received_at,
        received_by=request.received_by,
        notes=request.notes,
        materials=materials,
    )
    binder_resp = fetch_client_and_build_response(binder, db)
    return BinderReceiveResult(
        binder=binder_resp,
        intake=BinderIntakeResponse.model_validate(intake),
        is_new_binder=is_new_binder,
    )


@router.post(
    "/mark-ready-for-handover-bulk",
    response_model=list[BinderReadyForHandoverResponse],
    responses=BINDER_READY_BULK_RESPONSES,
)
def mark_ready_for_handover_bulk(
    request: BinderMarkReadyForHandoverBulkRequest,
    db: DBSession,
    user: CurrentUser,
):
    results = BinderLifecycleService(db).mark_ready_for_handover_bulk(
        client_record_id=request.client_record_id,
        until_period_year=request.until_period_year,
        until_period_month=request.until_period_month,
        changed_by_user_id=user.id,
    )
    return [
        BinderReadyForHandoverResponse(
            binder=fetch_client_and_build_response(binder, db),
            notification=notification,
        )
        for binder, notification in results
    ]


@router.post(
    "/handover-to-client-bulk",
    response_model=BinderHandoverResponse,
    status_code=status.HTTP_201_CREATED,
    responses=BINDER_HANDOVER_BULK_RESPONSES,
)
def handover_to_client_bulk(request: BinderHandoverRequest, db: DBSession, user: CurrentUser):
    handover = BinderHandoverService(db).create_handover(
        client_record_id=request.client_record_id,
        binder_ids=request.binder_ids,
        received_by_name=request.received_by_name,
        handed_over_at=request.handed_over_at,
        until_period_year=request.until_period_year,
        until_period_month=request.until_period_month,
        actor_id=user.id,
        notes=request.notes,
    )
    binder_ids = BinderHandoverRepository(db).get_binder_ids_for_handover(handover.id)
    return BinderHandoverResponse(
        id=handover.id,
        client_record_id=handover.client_record_id,
        received_by_name=handover.received_by_name,
        handed_over_at=handover.handed_over_at,
        until_period_year=handover.until_period_year,
        until_period_month=handover.until_period_month,
        binder_ids=binder_ids,
        notes=handover.notes,
        created_at=handover.created_at,
    )


@router.post(
    "/{binder_id}/receive-material",
    response_model=BinderResponse,
    responses=BINDER_ACTION_RESPONSES,
)
def receive_material(binder_id: PathId, db: DBSession, user: CurrentUser):
    binder = BinderLifecycleService(db).receive_material_by_id(
        binder_id=binder_id,
        changed_by_user_id=user.id,
    )
    return fetch_client_and_build_response(binder, db)


@router.post(
    "/{binder_id}/mark-full",
    response_model=BinderResponse,
    responses=BINDER_ACTION_RESPONSES,
)
def mark_full(binder_id: PathId, db: DBSession, user: CurrentUser):
    binder = BinderLifecycleService(db).mark_full(
        binder_id=binder_id,
        changed_by_user_id=user.id,
    )
    return fetch_client_and_build_response(binder, db)


@router.post(
    "/{binder_id}/reopen-capacity",
    response_model=BinderResponse,
    responses=BINDER_ACTION_RESPONSES,
)
def reopen_capacity(binder_id: PathId, db: DBSession, user: CurrentUser):
    binder = BinderLifecycleService(db).reopen_capacity(
        binder_id=binder_id,
        changed_by_user_id=user.id,
    )
    return fetch_client_and_build_response(binder, db)


@router.post(
    "/{binder_id}/mark-ready-for-handover",
    response_model=BinderReadyForHandoverResponse,
    responses=BINDER_ACTION_RESPONSES,
)
def mark_ready_for_handover(binder_id: PathId, db: DBSession, user: CurrentUser):
    binder, notification = BinderLifecycleService(db).mark_ready_for_handover(
        binder_id=binder_id,
        changed_by_user_id=user.id,
    )
    return BinderReadyForHandoverResponse(
        binder=fetch_client_and_build_response(binder, db),
        notification=notification,
    )


@router.post(
    "/{binder_id}/revert-ready-for-handover",
    response_model=BinderResponse,
    responses=BINDER_ACTION_RESPONSES,
)
def revert_ready_for_handover(binder_id: PathId, db: DBSession, user: CurrentUser):
    binder = BinderLifecycleService(db).revert_ready_for_handover(
        binder_id=binder_id,
        changed_by_user_id=user.id,
    )
    return fetch_client_and_build_response(binder, db)


@router.post(
    "/{binder_id}/handover-to-client",
    response_model=BinderResponse,
    responses=BINDER_ACTION_RESPONSES,
)
def handover_to_client(
    binder_id: PathId,
    request: BinderHandoverToClientRequest,
    db: DBSession,
    user: CurrentUser,
):
    binder = BinderLifecycleService(db).handover_to_client(
        binder_id=binder_id,
        changed_by_user_id=user.id,
        handed_over_at=request.handed_over_at,
        handover_recipient_name=request.handover_recipient_name,
    )
    return fetch_client_and_build_response(binder, db)
