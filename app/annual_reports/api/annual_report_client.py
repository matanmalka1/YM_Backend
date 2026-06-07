from fastapi import APIRouter, Depends, Query

from app.annual_reports.schemas.annual_report_responses import AnnualReportListResponse
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

clients_router = APIRouter(
    prefix="/clients",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@clients_router.get("/{client_record_id}/annual-reports", response_model=AnnualReportListResponse)
def list_client_reports(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """All annual reports for a client, sorted newest year first."""
    service = AnnualReportService(db)
    items, total = service.get_client_reports(client_record_id, page=page, page_size=page_size)
    return AnnualReportListResponse(items=items, page=page, page_size=page_size, total=total)
