from fastapi import APIRouter, Depends, Query

from app.annual_reports.schemas.annual_report_responses import AnnualReportListResponse
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

clients_router = APIRouter(
    prefix="/clients",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@clients_router.get(
    "/{client_record_id}/annual-reports",
    response_model=AnnualReportListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_client_reports(
    client_record_id: PathId,
    db: DBSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """All annual reports for a client, sorted newest year first."""
    service = AnnualReportService(db)
    items, total = service.get_client_reports(client_record_id, page=page, page_size=page_size)
    return AnnualReportListResponse(items=items, page=page, page_size=page_size, total=total)
