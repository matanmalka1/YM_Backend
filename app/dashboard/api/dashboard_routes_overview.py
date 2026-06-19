from fastapi import APIRouter, Depends

from app.dashboard.schemas.dashboard_extended import DashboardOverviewResponse
from app.dashboard.services.dashboard_overview_service import DashboardOverviewService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(db: DBSession, user: CurrentUser):
    """Get dashboard overview (ADVISOR only)."""
    service = DashboardOverviewService(db)
    overview = service.get_overview(user_role=user.role)
    return DashboardOverviewResponse(**overview)
