from fastapi import APIRouter, Depends

from app.annual_reports.api.annual_report_responses import REPORT_UPDATE_RESPONSES
from app.annual_reports.schemas.annual_report_detail import (
    AnnualReportDetailUpdateRequest,
    ReportDetailResponse,
)
from app.annual_reports.services.annual_report_detail_service import AnnualReportDetailService
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.openapi_responses import not_found_response
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get(
    "/{report_id}/details",
    response_model=ReportDetailResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_annual_report_detail(report_id: PathId, db: DBSession, user: CurrentUser):
    AnnualReportService(db).assert_report_exists(report_id)
    service = AnnualReportDetailService(db)
    detail = service.get_detail(report_id)
    if detail is None:
        return ReportDetailResponse(report_id=report_id)
    return ReportDetailResponse.model_validate(detail)


@router.patch(
    "/{report_id}/details",
    response_model=ReportDetailResponse,
    responses=REPORT_UPDATE_RESPONSES,
)
def update_annual_report_detail(
    report_id: PathId,
    request: AnnualReportDetailUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    AnnualReportService(db).assert_report_exists(report_id)
    service = AnnualReportDetailService(db)
    update_data = request.model_dump(exclude_unset=True)
    detail = service.update_detail(report_id, actor_id=user.id, **update_data)
    return ReportDetailResponse.model_validate(detail)
