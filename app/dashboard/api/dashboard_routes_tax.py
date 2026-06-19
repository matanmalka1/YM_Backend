from fastapi import APIRouter, Depends, Query

from app.dashboard.schemas.dashboard_tax import TaxSubmissionWidgetResponse
from app.dashboard.services.dashboard_tax_service import DashboardTaxService
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@router.get("/tax-submissions", response_model=TaxSubmissionWidgetResponse)
def get_tax_submission_widget(
    db: DBSession,
    user: CurrentUser,
    tax_year: int | None = Query(None, ge=1900),
):
    """Return tax submission statistics for the dashboard."""
    service = DashboardTaxService(db)
    response = service.get_submission_widget_data(tax_year=tax_year)
    return TaxSubmissionWidgetResponse(**response)
