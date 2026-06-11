from fastapi import APIRouter, Depends, Query, Response, status

from app.clients.create_policy import preview_vat_reporting_frequency
from app.clients.enums import ClientStatus
from app.clients.schemas.client import (
    ClientConflictInfo,
    ClientImpactPreviewRequest,
    ClientUpdateRequest,
    CreateClientRequest,
)
from app.clients.schemas.client_record_response import (
    ClientRecordListResponse,
    ClientRecordResponse,
    ClientSidebarListResponse,
    CreateClientRecordResponse,
)
from app.clients.schemas.impact import ClientCreationImpactResponse
from app.clients.services.client_lifecycle_service import ClientLifecycleService
from app.clients.services.client_query_service import ClientQueryService
from app.clients.services.client_update_service import ClientUpdateService
from app.clients.services.create_client_service import CreateClientService
from app.clients.services.impact_preview_service import compute_creation_impact
from app.common.enums import EntityType
from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "/preview-impact",
    # תיאור מפורט ל-OpenAPI
    summary="Preview creation impact",
    response_model=ClientCreationImpactResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def preview_creation_impact(
    request: ClientImpactPreviewRequest,
    db: DBSession,
):
    """מחזיר תצוגה מקדימה של הישויות שייווצרו אוטומטית עם פתיחת הלקוח."""
    return compute_creation_impact(
        db,
        entity_type=request.client.entity_type,
        vat_reporting_frequency=preview_vat_reporting_frequency(
            request.client.entity_type,
            request.client.vat_reporting_frequency,
        ),
        advance_payment_frequency=request.client.advance_payment_frequency,
    )


@router.post(
    "",
    response_model=CreateClientRecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
)
def create_client(
    request: CreateClientRequest,
    db: DBSession,
    user: CurrentUser,
):
    """Create a reporting entity and its first business in one request."""
    service = CreateClientService(db)
    return service.create_from_request(
        request,
        actor_id=user.id,
        actor_role=user.role,
    )


# ─── Read ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=ClientRecordListResponse)
def list_clients(
    db: DBSession,
    search: str | None = Query(None),
    status_filter: ClientStatus | None = Query(None, alias="status"),
    entity_type: EntityType | None = Query(None),
    accountant_id: int | None = Query(None, ge=1),
    tax_year: int | None = Query(None, ge=2000, le=2100),
    sort_by: str = Query(
        "full_name",
        pattern="^(full_name|created_at|status|entity_type)$",
    ),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List clients with optional search, status filter, and sorting."""
    service = ClientQueryService(db)
    result = service.list_full_clients(
        search=search,
        status=status_filter,
        entity_type=entity_type,
        accountant_id=accountant_id,
        tax_year=tax_year,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/sidebar", response_model=ClientSidebarListResponse)
def list_sidebar_clients(
    db: DBSession,
    search: str | None = Query(None),
    sort_by: str = Query("full_name", pattern="^(full_name|office_client_number)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
):
    service = ClientQueryService(db)
    return service.list_sidebar_clients(
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{client_id}",
    response_model=ClientRecordResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_client(
    client_id: int,
    db: DBSession,
    tax_year: int | None = Query(None, ge=2000, le=2100),
):
    """Get client by ID (client_id = ClientRecord.id)."""
    service = ClientQueryService(db)
    return service.get_full_client(client_id, tax_year=tax_year)


@router.get("/conflict/{id_number}", response_model=ClientConflictInfo)
def get_conflict_info(
    id_number: str,
    db: DBSession,
):
    """מחזיר מידע על קונפליקטים לת.ז. נתונה."""
    service = ClientQueryService(db)
    return service.get_conflict_info(id_number)


# ─── Update ───────────────────────────────────────────────────────────────────


@router.patch(
    "/{client_id}",
    response_model=ClientRecordResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def update_client(
    client_id: int,
    request: ClientUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    """Update client identity fields by ClientRecord.id."""
    ClientUpdateService(db).update_client(
        client_id,
        actor_id=user.id,
        actor_role=user.role,
        **request.model_dump(exclude_unset=True),
    )
    return ClientQueryService(db).get_full_client(client_id)


# ─── Delete / Restore ─────────────────────────────────────────────────────────


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def delete_client(client_id: int, db: DBSession, user: CurrentUser):
    """Soft-delete a client (ADVISOR only)."""
    ClientLifecycleService(db).delete_client(client_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{client_id}/restore",
    response_model=ClientRecordResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def restore_client(client_id: int, db: DBSession, user: CurrentUser):
    """Restore a soft-deleted client (ADVISOR only)."""
    ClientLifecycleService(db).restore_client(client_id, actor_id=user.id)
    return ClientQueryService(db).get_full_client_including_deleted(client_id)
