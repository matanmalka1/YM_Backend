"""Annual report tax calculation service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.annual_reports.integrations.tax_rules_registry import (
    get_default_resident_credit_points,
)
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.repositories.annual_report_credit_point_repository import (
    AnnualReportCreditPointRepository,
)
from app.annual_reports.repositories.annual_report_detail_repository import (
    AnnualReportDetailRepository,
)
from app.annual_reports.schemas.annual_report_financials import (
    BracketBreakdownItem,
    NationalInsuranceResponse,
    TaxCalculationResponse,
    TaxCalculationSaveResponse,
)
from app.annual_reports.services.annual_report_financial_summary_service import (
    AnnualReportFinancialSummaryService,
)
from app.annual_reports.services.annual_report_messages import (
    ANNUAL_REPORT_NOT_FOUND,
    TAX_CONFLICT_ERROR,
)
from app.annual_reports.services.annual_report_ni_engine import calculate_national_insurance
from app.annual_reports.services.annual_report_tax_engine import calculate_tax
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)

_PRE_SUBMISSION_STATUSES = {
    AnnualReportStatus.NOT_STARTED,
    AnnualReportStatus.COLLECTING_DOCS,
    AnnualReportStatus.IN_PREPARATION,
    AnnualReportStatus.PENDING_CLIENT,
}


def _decimal(value: float | int | Decimal | None) -> Decimal:
    return Decimal(str(value or 0))


class AnnualReportTaxService:
    """Calculate and persist annual-report tax outcomes."""

    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportRepository(db)
        self.detail_repo = AnnualReportDetailRepository(db)
        self.credit_point_repo = AnnualReportCreditPointRepository(db)
        self.vat_repo = VatWorkItemRepository(db)
        self.advance_repo = AdvancePaymentAggregationRepository(db)
        self.summary_service = AnnualReportFinancialSummaryService(db)
        self.client_repo = ClientRecordRepository(db)

    def _get_report_or_raise(self, report_id: int):
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return report

    def get_tax_calculation(self, report_id: int) -> TaxCalculationResponse:
        report = self._get_report_or_raise(report_id)
        return self.get_tax_calculation_for_report(report)

    def get_tax_calculation_for_report(self, report: AnnualReport) -> TaxCalculationResponse:
        summary = self.summary_service.get_financial_summary_for_report(report)
        detail = self.detail_repo.get_by_report_id(report.id)
        default_credit_points = get_default_resident_credit_points(report.tax_year)
        credit_points = float(
            self.credit_point_repo.total_points_by_report_id(
                report.id,
                default_resident_points=default_credit_points,
            )
        )
        pension_deduction = (
            float(detail.pension_contribution)
            if (detail and detail.pension_contribution is not None)
            else 0.0
        )
        donation_amount = (
            float(detail.donation_amount)
            if (detail and detail.donation_amount is not None)
            else 0.0
        )
        other_credits = (
            float(detail.other_credits) if (detail and detail.other_credits is not None) else 0.0
        )

        tax = calculate_tax(
            summary.taxable_income,
            report.tax_year,
            credit_points,
            pension_deduction,
            donation_amount,
            other_credits,
        )
        ni = calculate_national_insurance(
            summary.taxable_income, report.tax_year, report.client_type
        )
        net_profit = tax.taxable_income - tax.tax_after_credits
        vat_balance = self.vat_repo.sum_net_vat_by_client_record_year(
            report.client_record_id, report.tax_year
        )
        advances_paid = self.advance_repo.sum_paid_by_client_year(
            report.client_record_id, report.tax_year
        )

        total_liability = round(
            tax.tax_after_credits + ni.total + (vat_balance or 0) - advances_paid, 2
        )
        return TaxCalculationResponse(
            taxable_income=_decimal(tax.taxable_income),
            pension_deduction=_decimal(tax.pension_deduction),
            tax_before_credits=_decimal(tax.tax_before_credits),
            credit_points_value=_decimal(tax.credit_points_value),
            donation_credit=_decimal(tax.donation_credit),
            other_credits=_decimal(tax.other_credits),
            tax_after_credits=_decimal(tax.tax_after_credits),
            net_profit=_decimal(round(net_profit, 2)),
            effective_rate=_decimal(tax.effective_rate),
            national_insurance=NationalInsuranceResponse(
                base_amount=_decimal(ni.base_amount),
                high_amount=_decimal(ni.high_amount),
                total=_decimal(ni.total),
            ),
            brackets=[
                BracketBreakdownItem(
                    rate=_decimal(b.rate),
                    from_amount=_decimal(b.from_amount),
                    to_amount=_decimal(b.to_amount) if b.to_amount is not None else None,
                    taxable_in_bracket=_decimal(b.taxable_in_bracket),
                    tax_in_bracket=_decimal(b.tax_in_bracket),
                )
                for b in tax.brackets
            ],
            total_liability=_decimal(total_liability),
            total_credit_points=_decimal(tax.total_credit_points),
        )

    def save_tax_calculation(
        self,
        report_id: int,
        tax_due: Decimal | None,
        refund_due: Decimal | None,
    ) -> TaxCalculationSaveResponse:
        if tax_due is not None and refund_due is not None:
            raise AppError(
                TAX_CONFLICT_ERROR,
                ErrorCode.ANNUAL_REPORT_TAX_CONFLICT,
            )
        report = self._get_report_or_raise(report_id)
        updated = self.report_repo.update(report.id, tax_due=tax_due, refund_due=refund_due)
        return TaxCalculationSaveResponse(
            annual_report_id=report_id,
            tax_due=updated.tax_due,
            refund_due=updated.refund_due,
            saved_at=updated.updated_at,
        )

    def invalidate_tax_if_open(self, client_record_id: int, tax_year: int) -> None:
        client_record = self.client_repo.get_by_id(client_record_id)
        if not client_record:
            return
        report = self.report_repo.get_by_client_record_year(client_record.id, tax_year)
        if report and report.status in _PRE_SUBMISSION_STATUSES:
            self.report_repo.update(report.id, tax_due=None, refund_due=None)


__all__ = ["AnnualReportTaxService"]
