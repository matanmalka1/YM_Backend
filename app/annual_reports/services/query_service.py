from decimal import Decimal

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.annual_reports.integrations.tax_rules_registry import (
    get_default_resident_credit_points,
)
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportDetailResponse,
    AnnualReportListResponse,
    AnnualReportResponse,
    ScheduleEntryResponse,
    StatusHistoryResponse,
)
from app.annual_reports.services.financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.tax_service import (
    AnnualReportTaxService,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository

from .base import AnnualReportBaseService


class AnnualReportQueryService(AnnualReportBaseService):
    def get_report(self, report_id: int) -> AnnualReportResponse | None:
        report = self.repo.get_by_id(report_id)
        if not report:
            return None
        return self._to_responses([report])[0]

    def get_client_reports(
        self, client_record_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[AnnualReportResponse], int]:
        from app.core.exceptions import NotFoundError

        from .messages import ANNUAL_REPORT_CLIENT_NOT_FOUND

        client_record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if client_record is None:
            raise NotFoundError(
                ANNUAL_REPORT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                "ANNUAL_REPORT.CLIENT_NOT_FOUND",
            )
        reports = self.repo.list_by_client_record(client_record.id, page=page, page_size=page_size)
        total = self.repo.count_by_client_record(client_record.id)
        return self._to_responses(reports), total

    def list_reports(
        self,
        tax_year: int | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "tax_year",
        order: str = "desc",
        client_record_id: int | None = None,
        status: str | None = None,
    ) -> tuple[list[AnnualReportResponse], int]:
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
        return self._to_responses(items), total

    def get_season_summary(self, tax_year: int) -> dict:
        return self.repo.get_season_summary(tax_year)

    def get_overdue(
        self, tax_year: int | None = None, page: int = 1, page_size: int = 20
    ) -> AnnualReportListResponse:
        reports = self.repo.list_overdue(tax_year=tax_year, page=page, page_size=page_size)
        total = self.repo.count_overdue(tax_year=tax_year)
        return AnnualReportListResponse(
            items=self._to_responses(reports),
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_status_history(self, report_id: int) -> list:
        self._get_or_raise(report_id)
        return self.repo.get_status_history(report_id)

    def get_detail_report(self, report_id: int) -> AnnualReportDetailResponse | None:
        """Return report with schedules, history, financial summary, and detail fields. None if not found."""
        from app.annual_reports.repositories.credit_point_repository import (
            AnnualReportCreditPointRepository,
        )
        from app.annual_reports.repositories.detail_repository import (
            AnnualReportDetailRepository,
        )

        report = self.get_report(report_id)
        if report is None:
            return None

        schedules = self.repo.get_schedules(report_id)
        history = self.repo.get_status_history(report_id)
        financial_summary = AnnualReportFinancialSummaryService(
            self.db
        ).get_financial_summary(report_id)
        detail = AnnualReportDetailRepository(self.db).get_by_report_id(report_id)
        orm_report = self.repo.get_by_id(report_id)
        default_credit_points = get_default_resident_credit_points(
            orm_report.tax_year if orm_report else report.tax_year
        )
        credit_breakdown = AnnualReportCreditPointRepository(self.db).aggregate_breakdown(
            report_id,
            default_resident_points=default_credit_points,
        )

        response = AnnualReportDetailResponse(**report.model_dump())
        response.schedules = [ScheduleEntryResponse.model_validate(s) for s in schedules]
        response.status_history = [StatusHistoryResponse.model_validate(h) for h in history]
        response.total_income = financial_summary.total_income
        response.total_expenses = financial_summary.gross_expenses
        response.taxable_income = financial_summary.taxable_income

        if detail:
            response.client_approved_at = detail.client_approved_at
            response.internal_notes = detail.internal_notes
            response.amendment_reason = detail.amendment_reason
        response.credit_points = credit_breakdown["credit_points"]
        response.pension_credit_points = credit_breakdown["pension_credit_points"]
        response.life_insurance_credit_points = credit_breakdown["life_insurance_credit_points"]
        response.tuition_credit_points = credit_breakdown["tuition_credit_points"]
        if orm_report:
            response.tax_refund_amount = (
                float(orm_report.refund_due) if orm_report.refund_due is not None else None
            )
            response.tax_due_amount = (
                float(orm_report.tax_due) if orm_report.tax_due is not None else None
            )

        tax = AnnualReportTaxService(self.db).get_tax_calculation(report_id)
        response.profit = tax.net_profit
        advances_paid = Decimal(
            str(
                AdvancePaymentAggregationRepository(self.db).sum_paid_by_client_year(
                    orm_report.client_record_id, orm_report.tax_year
                )
            )
        )
        response.final_balance = tax.tax_after_credits - advances_paid

        return response
