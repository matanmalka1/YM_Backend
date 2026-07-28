from fastapi import APIRouter, Depends, Query

from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportListResponse,
    DefaultTaxYearResponse,
    SeasonSummaryResponse,
)
from app.annual_reports.services.annual_report_season_service import (
    get_active_annual_report_tax_year,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import ObligationStatus
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PositiveIntPath
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

season_router = APIRouter(
    prefix="/tax-year",
    tags=["annual-reports"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@season_router.get("/active/reports", response_model=AnnualReportListResponse)
def list_active_season_reports(
    db: DBSession,
    user: CurrentUser,
    client_record_id: int | None = Query(None),
    status: ObligationStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    tax_year = get_active_annual_report_tax_year()
    service = AnnualReportService(db)
    items, total = service.list_reports(
        tax_year=tax_year,
        page=page,
        page_size=page_size,
        client_record_id=client_record_id,
        status=status,
    )
    return AnnualReportListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@season_router.get("/active/summary", response_model=SeasonSummaryResponse)
def get_active_season_summary(db: DBSession, user: CurrentUser):
    tax_year = get_active_annual_report_tax_year()
    return AnnualReportService(db).get_season_summary_response(tax_year)


@season_router.get("/default", response_model=DefaultTaxYearResponse)
def get_default_tax_year(db: DBSession, user: CurrentUser):
    return AnnualReportService(db).get_default_tax_year_response()


@season_router.get("/{tax_year}/reports", response_model=AnnualReportListResponse)
def list_season_reports(
    tax_year: PositiveIntPath,
    db: DBSession,
    user: CurrentUser,
    client_record_id: int | None = Query(None),
    status: ObligationStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    """All reports for a given tax year — the advisor's season dashboard."""
    service = AnnualReportService(db)
    items, total = service.list_reports(
        tax_year=tax_year,
        page=page,
        page_size=page_size,
        client_record_id=client_record_id,
        status=status,
    )
    return AnnualReportListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@season_router.get("/{tax_year}/summary", response_model=SeasonSummaryResponse)
def get_season_summary(tax_year: PositiveIntPath, db: DBSession, user: CurrentUser):
    return AnnualReportService(db).get_season_summary_response(tax_year)
