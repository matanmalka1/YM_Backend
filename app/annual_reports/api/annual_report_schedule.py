from fastapi import APIRouter, Depends, Query

from app.annual_reports.api.responses import REPORT_SCHEDULE_WRITE_RESPONSES
from app.annual_reports.schemas.annual_report_requests import (
    ScheduleAddRequest,
    ScheduleCompleteRequest,
)
from app.annual_reports.schemas.annual_report_responses import ScheduleEntryResponse
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


@router.post(
    "/{report_id}/schedules",
    response_model=ScheduleEntryResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_SCHEDULE_WRITE_RESPONSES,
)
def add_schedule(report_id: int, body: ScheduleAddRequest, db: DBSession, user: CurrentUser):
    """Manually add a schedule to a report (auto-generated ones are created at report creation)."""
    service = AnnualReportService(db)
    entry = service.add_schedule(report_id, body.schedule, notes=body.notes)
    return ScheduleEntryResponse.model_validate(entry)


@router.get(
    "/{report_id}/schedules",
    response_model=PaginatedResponse[ScheduleEntryResponse],
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def list_schedules(
    report_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all schedules for a specific annual report."""
    service = AnnualReportService(db)
    all_schedules = service.get_schedules(report_id)
    total = len(all_schedules)
    start = (page - 1) * page_size
    items = [
        ScheduleEntryResponse.model_validate(e) for e in all_schedules[start : start + page_size]
    ]
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.post(
    "/{report_id}/schedules/complete",
    response_model=ScheduleEntryResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_SCHEDULE_WRITE_RESPONSES,
)
def complete_schedule(
    report_id: int, body: ScheduleCompleteRequest, db: DBSession, user: CurrentUser
):
    """Mark a specific schedule as complete."""
    service = AnnualReportService(db)
    entry = service.complete_schedule(report_id, body.schedule)
    return ScheduleEntryResponse.model_validate(entry)
