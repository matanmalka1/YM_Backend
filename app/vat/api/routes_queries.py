"""Routes: read-only queries — work items, audit trail."""

from fastapi import APIRouter, Depends, Query

from app.common.enums import VatType
from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole
from app.vat.api.serializers import (
    serialize_enriched_work_item,
    serialize_enriched_work_items,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.schemas.vat_audit import VatAuditLogResponse, VatAuditTrailResponse
from app.vat.schemas.vat_report import (
    VatPeriodOptionsResponse,
    VatWorkItemListResponse,
    VatWorkItemLookupResponse,
    VatWorkItemResponse,
    VatWorkItemStatusSummaryResponse,
)
from app.vat.services.vat_report_service import VatReportService

router = APIRouter(prefix="/vat", tags=["vat-reports"])


@router.get(
    "/work-items/lookup",
    response_model=VatWorkItemLookupResponse | None,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def lookup_work_item(
    db: DBSession,
    client_record_id: int = Query(...),
    period: str = Query(...),
):
    service = VatReportService(db)
    item = service.get_work_item_by_client_period(client_record_id, period)
    if not item:
        return None
    return VatWorkItemLookupResponse.model_validate(item)


@router.get(
    "/clients/{client_record_id}/period-options",
    response_model=VatPeriodOptionsResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_period_options(
    client_record_id: int,
    db: DBSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
):
    service = VatReportService(db)
    return service.get_period_options(client_record_id=client_record_id, year=year)


@router.get(
    "/work-items/status-summary",
    response_model=VatWorkItemStatusSummaryResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def get_status_summary(
    db: DBSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
    period_type: VatType | None = Query(None),
    client_name: str | None = Query(None),
):
    service = VatReportService(db)
    return service.get_status_summary(
        year=year,
        period_type=period_type,
        client_name=client_name,
    )


@router.get(
    "/work-items/{item_id}",
    response_model=VatWorkItemResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def get_work_item(item_id: int, db: DBSession, current_user: CurrentUser):
    service = VatReportService(db)
    enriched = service.get_work_item_enriched(item_id)
    return serialize_enriched_work_item(
        enriched["item"],
        office_client_number_map=enriched["office_client_number_map"],
        name_map=enriched["name_map"],
        id_number_map=enriched["id_number_map"],
        status_map=enriched["status_map"],
        user_map=enriched["user_map"],
        user_role=current_user.role,
    )


@router.get(
    "/clients/{client_record_id}/work-items",
    response_model=VatWorkItemListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_client_work_items(
    client_record_id: int,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=200),
):
    service = VatReportService(db)
    enriched = service.get_client_items_enriched(
        client_record_id,
        page=page,
        page_size=page_size,
    )
    items = serialize_enriched_work_items(
        enriched["items"],
        enriched=enriched,
        user_role=current_user.role,
    )
    return VatWorkItemListResponse(
        items=items, total=enriched["total"], page=page, page_size=page_size
    )


@router.get(
    "/work-items",
    response_model=VatWorkItemListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_work_items(
    db: DBSession,
    current_user: CurrentUser,
    status_filter: VatWorkItemStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    period: str | None = Query(None),
    period_type: VatType | None = Query(None),
    client_name: str | None = Query(None),
):
    service = VatReportService(db)
    enriched = service.get_list_enriched(
        status_filter=status_filter,
        page=page,
        page_size=page_size,
        period=period,
        period_type=period_type,
        client_name=client_name,
    )
    items = serialize_enriched_work_items(
        enriched["items"],
        enriched=enriched,
        user_role=current_user.role,
    )
    return VatWorkItemListResponse(
        items=items, total=enriched["total"], page=page, page_size=page_size
    )


@router.get(
    "/work-items/{item_id}/audit",
    response_model=VatAuditTrailResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description='פריט עבודה למע"מ לא נמצא'),
)
def get_audit_trail(
    item_id: int,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    service = VatReportService(db)
    enriched = service.get_audit_trail_enriched(item_id, page, page_size)
    items = []
    for e in enriched["entries"]:
        row = VatAuditLogResponse.model_validate(e)
        row.performed_by_name = enriched["user_map"].get(e.performed_by)
        items.append(row)
    return VatAuditTrailResponse(
        items=items, total=enriched["total"], page=page, page_size=page_size
    )
