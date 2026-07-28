from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.businesses.repositories.business_repository import BusinessRepository
from app.common.enums import ObligationStatus
from app.utils.time_utils import israel_today


class DashboardTaxService:
    """Tax-specific dashboard widget data."""

    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportRepository(db)
        self.business_repo = BusinessRepository(db)

    def get_submission_widget_data(
        self,
        tax_year: int | None = None,
    ) -> dict:
        """Get annual report submission statistics."""
        if tax_year is None:
            tax_year = israel_today().year

        total_clients = self.business_repo.count(status="active")

        # Submitted is now one status; this used to add `submitted` and `closed`,
        # which were two names for the same finished state.
        submitted = self.report_repo.count_by_status(
            ObligationStatus.SUBMITTED, tax_year=tax_year
        )

        # IN_PROGRESS statuses
        in_progress = self.report_repo.count_by_status(
            ObligationStatus.IN_PROGRESS, tax_year=tax_year
        ) + self.report_repo.count_by_status(ObligationStatus.AWAITING_VERIFICATION, tax_year=tax_year)

        # MATERIAL_COLLECTION statuses
        material_collection = self.report_repo.count_by_status(
            ObligationStatus.AWAITING_INPUT, tax_year=tax_year
        )

        not_started = max(0, total_clients - (submitted + in_progress + material_collection))

        submission_percentage = (
            round((submitted / total_clients) * 100, 1) if total_clients > 0 else 0.0
        )

        financials = self.report_repo.sum_financials_by_year(tax_year)

        return {
            "tax_year": tax_year,
            "total_clients": total_clients,
            "reports_submitted": submitted,
            "reports_in_progress": in_progress,
            "reports_not_started": not_started,
            "submission_percentage": submission_percentage,
            "total_refund_due": financials["total_refund_due"],
            "total_tax_due": financials["total_tax_due"],
        }
