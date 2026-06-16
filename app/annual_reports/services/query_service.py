from app.core.error_codes import ErrorCode
from decimal import Decimal

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.annual_reports.integrations.tax_rules_registry import (
    get_default_resident_credit_points,
)
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportAuditEntry,
    AnnualReportDetailResponse,
    AnnualReportListItem,
    AnnualReportListResponse,
    AnnualReportResponse,
    AnnualReportTaxCalculationResponse,
    ScheduleEntryResponse,
)
from app.annual_reports.services.financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.tax_service import (
    AnnualReportTaxService,
)
from .base import AnnualReportBaseService


class AnnualReportQueryService(AnnualReportBaseService):
    def get_report(self, report_id: int) -> AnnualReportResponse | None:
        report = self.repo.get_by_id(report_id)
        if not report:
            return None
        return self._to_responses([report])[0]

    def get_client_reports(
        self, client_record_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[AnnualReportListItem], int]:
        from app.core.exceptions import NotFoundError

        from .messages import ANNUAL_REPORT_CLIENT_NOT_FOUND

        client_record = self.client_repo.get_by_id(client_record_id)
        if client_record is None:
            raise NotFoundError(
                ANNUAL_REPORT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                ErrorCode.ANNUAL_REPORT_CLIENT_NOT_FOUND,
            )
        reports = self.repo.list_by_client_record(client_record.id, page=page, page_size=page_size)
        total = self.repo.count_by_client_record(client_record.id)
        return self._to_list_items(reports), total

    def list_reports(
        self,
        tax_year: int | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "tax_year",
        order: str = "desc",
        client_record_id: int | None = None,
        status: str | None = None,
    ) -> tuple[list[AnnualReportListItem], int]:
        if tax_year is not None:
            items = self.repo.list_by_tax_year(
                tax_year,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                order=order,
                client_record_id=client_record_id,
                status=status,
            )
            total = self.repo.count_by_tax_year(
                tax_year, client_record_id=client_record_id, status=status
            )
        else:
            items = self.repo.list_all(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                order=order,
                client_record_id=client_record_id,
                status=status,
            )
            total = self.repo.count_all(client_record_id=client_record_id, status=status)
        return self._to_list_items(items), total

    def get_season_summary(self, tax_year: int) -> dict:
        return self.repo.get_season_summary(tax_year)

    def get_overdue(
        self, tax_year: int | None = None, page: int = 1, page_size: int = 20
    ) -> AnnualReportListResponse:
        reports = self.repo.list_overdue(tax_year=tax_year, page=page, page_size=page_size)
        total = self.repo.count_overdue(tax_year=tax_year)
        return AnnualReportListResponse(
            items=self._to_list_items(reports),
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_report_audit(self, report_id: int) -> list:
        self._get_or_raise(report_id)
        return self.repo.list_status_audit_entries(report_id)

    def get_detail_report(self, report_id: int) -> AnnualReportDetailResponse | None:
        """Return report with schedules, status audit entries, financial summary, and detail fields. None if not found."""
        from app.annual_reports.repositories.credit_point_repository import (
            AnnualReportCreditPointRepository,
        )
        from app.annual_reports.repositories.detail_repository import (
            AnnualReportDetailRepository,
        )

        orm_report = self.repo.get_by_id(report_id)
        if orm_report is None:
            return None
        report = self._to_responses([orm_report])[0]

        schedules = self.repo.get_schedules(report_id)
        status_audit = self.repo.list_status_audit_entries(report_id)
        financial_summary = AnnualReportFinancialSummaryService(
            self.db
        ).get_financial_summary_for_report(orm_report)
        detail = AnnualReportDetailRepository(self.db).get_by_report_id(report_id)
        default_credit_points = get_default_resident_credit_points(orm_report.tax_year)
        credit_breakdown = AnnualReportCreditPointRepository(self.db).aggregate_breakdown(
            report_id,
            default_resident_points=default_credit_points,
        )

        response = AnnualReportDetailResponse(**report.model_dump())
        response.schedules = [ScheduleEntryResponse.model_validate(s) for s in schedules]
        response.status_audit = [AnnualReportAuditEntry.model_validate(h) for h in status_audit]

        if detail:
            response.client_approved_at = detail.client_approved_at
            response.internal_notes = detail.internal_notes
            response.amendment_reason = detail.amendment_reason

        tax = AnnualReportTaxService(self.db).get_tax_calculation_for_report(orm_report)
        advances_paid = Decimal(
            str(
                AdvancePaymentAggregationRepository(self.db).sum_paid_by_client_year(
                    orm_report.client_record_id, orm_report.tax_year
                )
            )
        )
        response.tax_calculation = AnnualReportTaxCalculationResponse(
            total_income=financial_summary.total_income,
            total_expenses=financial_summary.gross_expenses,
            recognized_expenses=financial_summary.recognized_expenses,
            taxable_income=financial_summary.taxable_income,
            profit=tax.net_profit,
            tax_after_credits=tax.tax_after_credits,
            final_balance=tax.tax_after_credits - advances_paid,
            credit_points=credit_breakdown["credit_points"],
            pension_credit_points=credit_breakdown["pension_credit_points"],
            life_insurance_credit_points=credit_breakdown["life_insurance_credit_points"],
            tuition_credit_points=credit_breakdown["tuition_credit_points"],
        )

        return response
