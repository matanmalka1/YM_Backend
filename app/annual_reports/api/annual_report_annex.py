"""Endpoints for annex (schedule) data lines."""

from fastapi import APIRouter, Depends, Query, status

from app.annual_reports.api.responses import REPORT_LINE_WRITE_RESPONSES
from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.schemas.annual_report_annex import (
    AnnexDataAddRequest,
    AnnexDataLineResponse,
    AnnexDataUpdateRequest,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.api_types import PaginatedResponse
from app.core.openapi_responses import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{report_id}/annex/{schedule}",
    response_model=PaginatedResponse[AnnexDataLineResponse],
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def list_annex_lines(
    report_id: int,
    schedule: AnnualReportSchedule,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    svc = AnnualReportService(db)
    all_lines = svc.get_annex_lines(report_id, schedule)
    total = len(all_lines)
    start = (page - 1) * page_size
    items = all_lines[start : start + page_size]
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/{report_id}/annex/{schedule}",
    response_model=AnnexDataLineResponse,
    status_code=status.HTTP_201_CREATED,
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def add_annex_line(
    report_id: int,
    schedule: AnnualReportSchedule,
    body: AnnexDataAddRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportService(db)
    return svc.add_annex_line(report_id, schedule, body.data, body.notes, actor_id=user.id)


@router.patch(
    "/{report_id}/annex/{schedule}/{line_id}",
    response_model=AnnexDataLineResponse,
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def update_annex_line(
    report_id: int,
    schedule: AnnualReportSchedule,
    line_id: int,
    body: AnnexDataUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportService(db)
    return svc.update_annex_line(report_id, line_id, body.data, body.notes, actor_id=user.id)


@router.delete(
    "/{report_id}/annex/{schedule}/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_LINE_WRITE_RESPONSES,
)
def delete_annex_line(
    report_id: int,
    schedule: AnnualReportSchedule,
    line_id: int,
    db: DBSession,
    user: CurrentUser,
):
    svc = AnnualReportService(db)
    svc.delete_annex_line(report_id, line_id, actor_id=user.id)
