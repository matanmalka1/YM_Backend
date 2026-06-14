from fastapi import APIRouter, Depends, Query, Response, status

from app.annual_reports.api.responses import (
    REPORT_AMEND_RESPONSES,
    REPORT_CREATE_RESPONSES,
)
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.schemas.annual_report_requests import (
    AmendRequest,
    AnnualReportCreateRequest,
)
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportDetailResponse,
    AnnualReportListResponse,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.exceptions import NotFoundError
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.post(
    "",
    response_model=AnnualReportDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses=REPORT_CREATE_RESPONSES,
)
def create_annual_report(body: AnnualReportCreateRequest, db: DBSession, user: CurrentUser):
    """Create a new annual income tax report for a client legal entity."""
    service = AnnualReportService(db)
    orm_report = service.create_report(
        client_record_id=body.client_record_id,
        tax_year=body.tax_year,
        client_type=body.client_type,
        created_by=user.id,
        created_by_name=user.full_name,
        deadline_type=body.deadline_type,
        assigned_to=body.assigned_to,
        notes=body.notes,
        submission_method=body.submission_method.value if body.submission_method else None,
        extension_reason=body.extension_reason.value if body.extension_reason else None,
        has_rental_income=body.has_rental_income,
        has_capital_gains=body.has_capital_gains,
        has_foreign_income=body.has_foreign_income,
        has_depreciation=body.has_depreciation,
    )
    return service.get_detail_report(orm_report.id)


@router.get("", response_model=AnnualReportListResponse)
def list_annual_reports(
    db: DBSession,
    user: CurrentUser,
    tax_year: int | None = Query(None),
    client_record_id: int | None = Query(None),
    status: AnnualReportStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    sort_by: str = Query(
        "tax_year",
        pattern="^(tax_year|status|filing_deadline|created_at|client_record_id)$",
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """List annual reports (optionally filter by tax_year, client_record_id, status)."""
    service = AnnualReportService(db)
    items, total = service.list_reports(
        tax_year=tax_year,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
        client_record_id=client_record_id,
        status=status,
    )
    return AnnualReportListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/overdue", response_model=AnnualReportListResponse)
def list_overdue(
    db: DBSession,
    user: CurrentUser,
    tax_year: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """Reports past their filing deadline that have not been submitted."""
    service = AnnualReportService(db)
    return service.get_overdue(tax_year=tax_year, page=page, page_size=page_size)


@router.get(
    "/{report_id}",
    response_model=AnnualReportDetailResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_annual_report(report_id: PathId, db: DBSession, user: CurrentUser):
    """Get a single report with its schedule entries and status audit entries."""
    service = AnnualReportService(db)
    detail = service.get_detail_report(report_id)
    if detail is None:
        raise NotFoundError("הדוח לא נמצא", "ANNUAL_REPORT.NOT_FOUND")
    return detail


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def delete_annual_report(report_id: PathId, db: DBSession, user: CurrentUser):
    """Soft-delete an annual report (ADVISOR only)."""
    service = AnnualReportService(db)
    deleted = service.delete_report(report_id, actor_id=user.id, actor_name=user.full_name)
    if not deleted:
        raise NotFoundError("הדוח לא נמצא", "ANNUAL_REPORT.NOT_FOUND")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{report_id}/amend",
    response_model=AnnualReportDetailResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_AMEND_RESPONSES,
)
def amend_annual_report(report_id: PathId, body: AmendRequest, db: DBSession, user: CurrentUser):
    """Reopen a SUBMITTED report for amendment and record the reason (ADVISOR only)."""
    service = AnnualReportService(db)
    return service.amend_report(
        report_id,
        reason=body.reason,
        actor_id=user.id,
        actor_name=user.full_name,
    )
