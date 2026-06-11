from fastapi import APIRouter, Depends

from app.annual_reports.schemas.annual_report_detail import (
    AnnualReportDetailUpdateRequest,
    ReportDetailResponse,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.detail_service import AnnualReportDetailService
from app.core.exceptions import not_found_response
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-report-detail"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


def _enrich_detail_response(response: ReportDetailResponse, db) -> ReportDetailResponse:
    from app.annual_reports.repositories.annual_report_repository import (
        AnnualReportRepository,
    )

    report = AnnualReportRepository(db).get_by_id(response.report_id)
    if report:
        response.tax_refund_amount = (
            float(report.refund_due) if report.refund_due is not None else None
        )
        response.tax_due_amount = float(report.tax_due) if report.tax_due is not None else None
    return response


@router.get(
    "/{report_id}/details",
    response_model=ReportDetailResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def get_annual_report_detail(report_id: int, db: DBSession, user: CurrentUser):
    AnnualReportService(db).assert_report_exists(report_id)
    service = AnnualReportDetailService(db)
    detail = service.get_detail(report_id)
    if detail is None:
        return _enrich_detail_response(ReportDetailResponse(report_id=report_id), db)
    return _enrich_detail_response(ReportDetailResponse.model_validate(detail), db)


@router.patch(
    "/{report_id}/details",
    response_model=ReportDetailResponse,
    responses=not_found_response(description="הדוח המבוקש לא נמצא"),
)
def update_annual_report_detail(
    report_id: int,
    request: AnnualReportDetailUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    AnnualReportService(db).assert_report_exists(report_id)
    service = AnnualReportDetailService(db)
    update_data = request.model_dump(exclude_unset=True)
    detail = service.update_detail(report_id, actor_id=user.id, **update_data)
    return _enrich_detail_response(ReportDetailResponse.model_validate(detail), db)
