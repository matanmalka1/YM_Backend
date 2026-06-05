from datetime import date

from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.businesses.repositories.business_repository import BusinessRepository


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
            tax_year = date.today().year

        total_clients = self.business_repo.count(status="active")

        # TRANSMITTED / fully done statuses
        submitted = self.report_repo.count_by_status(
            AnnualReportStatus.SUBMITTED, tax_year=tax_year
        ) + self.report_repo.count_by_status(AnnualReportStatus.CLOSED, tax_year=tax_year)

        # IN_PROGRESS statuses
        in_progress = self.report_repo.count_by_status(
            AnnualReportStatus.IN_PREPARATION, tax_year=tax_year
        ) + self.report_repo.count_by_status(AnnualReportStatus.PENDING_CLIENT, tax_year=tax_year)

        # MATERIAL_COLLECTION statuses
        material_collection = self.report_repo.count_by_status(
            AnnualReportStatus.COLLECTING_DOCS, tax_year=tax_year
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
