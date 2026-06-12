from fastapi import APIRouter, Depends

from app.annual_reports.api.responses import REPORT_TRANSITION_RESPONSES
from app.annual_reports.schemas.annual_report_requests import StageTransitionRequest
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportDetailResponse,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/annual-reports",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.post(
    "/{report_id}/transition",
    response_model=AnnualReportDetailResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=REPORT_TRANSITION_RESPONSES,
)
def transition_stage(
    report_id: int, body: StageTransitionRequest, db: DBSession, user: CurrentUser
):
    service = AnnualReportService(db)
    return service.transition_stage(
        report_id=report_id,
        to_stage=body.to_stage,
        changed_by=user.id,
        changed_by_name=user.full_name,
    )
