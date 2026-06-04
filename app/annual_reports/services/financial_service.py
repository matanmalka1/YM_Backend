"""Annual report financial service: CRUD, tax calculation, readiness."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.annual_reports.domain.expense_rules import default_recognition_rate
from app.annual_reports.integrations.tax_rules_registry import (
    get_default_resident_credit_points,
)
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.repositories.credit_point_repository import (
    AnnualReportCreditPointRepository,
)
from app.annual_reports.repositories.detail_repository import (
    AnnualReportDetailRepository,
)
from app.annual_reports.repositories.expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.schemas.annual_report_financials import (
    BracketBreakdownItem,
    ExpenseLineResponse,
    FinancialSummaryResponse,
    IncomeLineResponse,
    NationalInsuranceResponse,
    ReadinessCheckResponse,
    TaxCalculationResponse,
    TaxCalculationSaveResponse,
)
from app.annual_reports.services.labels import SCHEDULE_LABELS
from app.annual_reports.services.messages import (
    ANNUAL_REPORT_NOT_FOUND,
    CLIENT_CLOSED_CREATE_WORK_ERROR,
    CLIENT_FROZEN_CREATE_WORK_ERROR,
    CLIENT_NOT_APPROVED_REPORT_ISSUE,
    EXPENSE_LINE_NOT_FOUND,
    INCOME_LINE_NOT_FOUND,
    INCOMPLETE_REQUIRED_SCHEDULE_ISSUE,
    INVALID_EXPENSE_CATEGORY_ERROR,
    INVALID_INCOME_SOURCE_ERROR,
    MISSING_REPORT_INCOME_ISSUE,
    MISSING_TAX_CALCULATION_ISSUE,
    TAX_CONFLICT_ERROR,
)
from app.annual_reports.services.ni_engine import calculate_national_insurance
from app.annual_reports.services.tax_engine import calculate_tax
from app.audit.constants import (
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.services.entity_audit_writer import EntityAuditWriter
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.vat_reports.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)

_PRE_SUBMISSION_STATUSES = {
    AnnualReportStatus.NOT_STARTED,
    AnnualReportStatus.COLLECTING_DOCS,
    AnnualReportStatus.IN_PREPARATION,
    AnnualReportStatus.PENDING_CLIENT,
}


def audit_scalar(value):
    return value.value if hasattr(value, "value") else str(value) if value is not None else None


def income_line_snapshot(line) -> dict:
    return {
        "line_id": line.id,
        "source_type": audit_scalar(line.source_type),
        "amount": str(line.amount),
        "description": line.description,
    }


def expense_line_snapshot(line) -> dict:
    return {
        "line_id": line.id,
        "category": audit_scalar(line.category),
        "amount": str(line.amount),
        "description": line.description,
    }


class AnnualReportFinancialService:
    """Single service for all financial operations on an annual report."""

    _SCHEDULE_LABELS = SCHEDULE_LABELS

    def __init__(self, db: Session):
        self.db = db
        self.income_repo = AnnualReportIncomeRepository(db)
        self.expense_repo = AnnualReportExpenseRepository(db)
        self.report_repo = AnnualReportRepository(db)
        self.detail_repo = AnnualReportDetailRepository(db)
        self.credit_point_repo = AnnualReportCreditPointRepository(db)
        self.vat_repo = VatWorkItemRepository(db)
        self.advance_repo = AdvancePaymentAggregationRepository(db)
        self.business_repo = BusinessRepository(db)

    def _get_report_or_raise(self, report_id: int):
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                "ANNUAL_REPORT.NOT_FOUND",
            )
        return report

    def _assert_client_allows_create(self, client_record_id: int) -> None:
        client_record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if client_record and client_record.status == ClientStatus.CLOSED:
            raise ForbiddenError(CLIENT_CLOSED_CREATE_WORK_ERROR, "CLIENT.CLOSED")
        if client_record and client_record.status == ClientStatus.FROZEN:
            raise ForbiddenError(CLIENT_FROZEN_CREATE_WORK_ERROR, "CLIENT.FROZEN")

    def add_income(
        self,
        report_id: int,
        source_type: str,
        amount: Decimal,
        description: str | None = None,
        actor_id: int | None = None,
    ) -> IncomeLineResponse:
        report = self._get_report_or_raise(report_id)
        self._assert_client_allows_create(report.client_record_id)
        valid_sources = {e.value for e in IncomeSourceType}
        if source_type not in valid_sources:
            raise AppError(
                INVALID_INCOME_SOURCE_ERROR.format(source_type=source_type),
                "ANNUAL_REPORT.INVALID_TYPE",
            )
        line = self.income_repo.add_line(
            report_id, IncomeSourceType(source_type), amount, description
        )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_INCOME_ADDED,
            new_value={
                "source_type": source_type,
                "amount": str(amount),
                "description": description,
            },
        )
        return IncomeLineResponse.model_validate(line)

    def update_income(
        self, report_id: int, line_id: int, actor_id: int | None = None, **fields
    ) -> IncomeLineResponse:
        self._get_report_or_raise(report_id)
        if "source_type" in fields and fields["source_type"] is not None:
            valid_sources = {e.value for e in IncomeSourceType}
            if fields["source_type"] not in valid_sources:
                raise AppError(
                    INVALID_INCOME_SOURCE_ERROR.format(source_type=fields["source_type"]),
                    "ANNUAL_REPORT.INVALID_TYPE",
                )
            fields["source_type"] = IncomeSourceType(fields["source_type"])
        old_line = self.income_repo.get_by_report_and_id(report_id, line_id)
        if not old_line:
            raise NotFoundError(
                INCOME_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        old_value = income_line_snapshot(old_line)
        line = self.income_repo.update_for_report(
            report_id, line_id, **{k: v for k, v in fields.items() if v is not None}
        )
        if not line:
            raise NotFoundError(
                INCOME_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_INCOME_UPDATED,
            old_value=old_value,
            new_value={k: audit_scalar(v) for k, v in fields.items()},
        )
        return IncomeLineResponse.model_validate(line)

    def delete_income(self, report_id: int, line_id: int, actor_id: int | None = None) -> None:
        self._get_report_or_raise(report_id)
        line = self.income_repo.get_by_report_and_id(report_id, line_id)
        if not line:
            raise NotFoundError(
                INCOME_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        old_value = income_line_snapshot(line)
        if not self.income_repo.delete_for_report(report_id, line_id):
            raise NotFoundError(
                INCOME_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_INCOME_DELETED,
            old_value=old_value,
            note=f"line_id={line_id}",
        )

    def add_expense(
        self,
        report_id: int,
        category: str,
        amount: Decimal,
        description: str | None = None,
        recognition_rate: Decimal | None = None,
        external_document_reference: str | None = None,
        supporting_document_id: int | None = None,
        actor_id: int | None = None,
    ) -> ExpenseLineResponse:
        report = self._get_report_or_raise(report_id)
        self._assert_client_allows_create(report.client_record_id)
        valid_categories = {e.value for e in ExpenseCategoryType}
        if category not in valid_categories:
            raise AppError(
                INVALID_EXPENSE_CATEGORY_ERROR.format(category=category),
                "ANNUAL_REPORT.INVALID_TYPE",
            )
        expense_category = ExpenseCategoryType(category)
        rate = (
            recognition_rate
            if recognition_rate is not None
            else default_recognition_rate(expense_category)
        )
        line = self.expense_repo.add_line(
            annual_report_id=report_id,
            category=expense_category,
            amount=amount,
            recognition_rate=rate,
            description=description,
            external_document_reference=external_document_reference,
            supporting_document_id=supporting_document_id,
        )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_EXPENSE_ADDED,
            new_value={
                "category": category,
                "amount": str(amount),
                "description": description,
            },
        )
        return ExpenseLineResponse.model_validate(line)

    def update_expense(
        self, report_id: int, line_id: int, actor_id: int | None = None, **fields
    ) -> ExpenseLineResponse:
        self._get_report_or_raise(report_id)
        if "category" in fields and fields["category"] is not None:
            valid_categories = {e.value for e in ExpenseCategoryType}
            if fields["category"] not in valid_categories:
                raise AppError(
                    INVALID_EXPENSE_CATEGORY_ERROR.format(category=fields["category"]),
                    "ANNUAL_REPORT.INVALID_TYPE",
                )
            fields["category"] = ExpenseCategoryType(fields["category"])
        old_line = self.expense_repo.get_by_report_and_id(report_id, line_id)
        if not old_line:
            raise NotFoundError(
                EXPENSE_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        old_value = expense_line_snapshot(old_line)
        line = self.expense_repo.update_for_report(
            report_id, line_id, **{k: v for k, v in fields.items() if v is not None}
        )
        if not line:
            raise NotFoundError(
                EXPENSE_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_EXPENSE_UPDATED,
            old_value=old_value,
            new_value={k: audit_scalar(v) for k, v in fields.items()},
        )
        return ExpenseLineResponse.model_validate(line)

    def delete_expense(self, report_id: int, line_id: int, actor_id: int | None = None) -> None:
        self._get_report_or_raise(report_id)
        line = self.expense_repo.get_by_report_and_id(report_id, line_id)
        if not line:
            raise NotFoundError(
                EXPENSE_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        old_value = expense_line_snapshot(line)
        if not self.expense_repo.delete_for_report(report_id, line_id):
            raise NotFoundError(
                EXPENSE_LINE_NOT_FOUND.format(line_id=line_id),
                "ANNUAL_REPORT.LINE_NOT_FOUND",
            )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_EXPENSE_DELETED,
            old_value=old_value,
            note=f"line_id={line_id}",
        )

    def get_financial_summary(self, report_id: int) -> FinancialSummaryResponse:
        return self._build_financial_summary(report_id)

    def _build_financial_summary(self, report_id: int) -> FinancialSummaryResponse:
        self._get_report_or_raise(report_id)
        income_lines = self.income_repo.list_by_report(report_id)
        expense_lines = self.expense_repo.list_by_report(report_id)
        total_income = self.income_repo.total_income(report_id)
        gross_expenses = self.expense_repo.total_expenses(report_id)
        recognized_expenses = self.expense_repo.total_recognized_expenses(report_id)
        return FinancialSummaryResponse(
            annual_report_id=report_id,
            total_income=float(total_income),
            gross_expenses=float(gross_expenses),
            recognized_expenses=float(recognized_expenses),
            taxable_income=float(total_income - recognized_expenses),
            income_lines=[IncomeLineResponse.model_validate(line) for line in income_lines],
            expense_lines=[ExpenseLineResponse.model_validate(line) for line in expense_lines],
        )

    def get_tax_calculation(self, report_id: int) -> TaxCalculationResponse:
        report = self._get_report_or_raise(report_id)
        summary = self.get_financial_summary(report_id)
        detail = self.detail_repo.get_by_report_id(report_id)
        default_credit_points = get_default_resident_credit_points(report.tax_year)
        credit_points = float(
            self.credit_point_repo.total_points_by_report_id(
                report_id,
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
            taxable_income=tax.taxable_income,
            pension_deduction=tax.pension_deduction,
            tax_before_credits=tax.tax_before_credits,
            credit_points_value=tax.credit_points_value,
            donation_credit=tax.donation_credit,
            other_credits=tax.other_credits,
            tax_after_credits=tax.tax_after_credits,
            net_profit=round(net_profit, 2),
            effective_rate=tax.effective_rate,
            national_insurance=NationalInsuranceResponse(
                base_amount=ni.base_amount,
                high_amount=ni.high_amount,
                total=ni.total,
            ),
            brackets=[
                BracketBreakdownItem(
                    rate=b.rate,
                    from_amount=b.from_amount,
                    to_amount=b.to_amount,
                    taxable_in_bracket=b.taxable_in_bracket,
                    tax_in_bracket=b.tax_in_bracket,
                )
                for b in tax.brackets
            ],
            total_liability=total_liability,
            total_credit_points=tax.total_credit_points,
        )

    def get_readiness_check(self, report_id: int) -> ReadinessCheckResponse:
        self._get_report_or_raise(report_id)
        issues: list[str] = []
        passed = 0

        schedules = self.report_repo.get_schedules(report_id)
        required = [s for s in schedules if s.is_required]
        if required:
            incomplete = [s for s in required if not s.is_complete]
            if incomplete:
                for schedule in incomplete:
                    label = self._SCHEDULE_LABELS.get(
                        schedule.schedule.value, schedule.schedule.value
                    )
                    issues.append(INCOMPLETE_REQUIRED_SCHEDULE_ISSUE.format(label=label))
            else:
                passed += 1
        else:
            passed += 1

        total_income = self.income_repo.total_income(report_id)
        if total_income == 0:
            issues.append(MISSING_REPORT_INCOME_ISSUE)
        else:
            passed += 1

        detail = self.detail_repo.get_by_report_id(report_id)
        report = self._get_report_or_raise(report_id)
        if report.tax_due is None and report.refund_due is None:
            issues.append(MISSING_TAX_CALCULATION_ISSUE)
        else:
            passed += 1

        if not detail or not detail.client_approved_at:
            issues.append(CLIENT_NOT_APPROVED_REPORT_ISSUE)
        else:
            passed += 1

        completion_pct = round(passed / 4 * 100, 1)
        return ReadinessCheckResponse(
            annual_report_id=report_id,
            is_ready=len(issues) == 0,
            issues=issues,
            completion_pct=completion_pct,
        )

    def save_tax_calculation(
        self,
        report_id: int,
        tax_due: Decimal | None,
        refund_due: Decimal | None,
    ) -> TaxCalculationSaveResponse:
        """Persist computed tax_due / refund_due to the annual report record."""
        if tax_due is not None and refund_due is not None:
            raise AppError(
                TAX_CONFLICT_ERROR,
                "ANNUAL_REPORT.TAX_CONFLICT",
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
        """Clear saved tax_due / refund_due when advances change before submission."""
        client_record = ClientRecordRepository(self.report_repo.db).get_by_id(client_record_id)
        if not client_record:
            return
        report = self.report_repo.get_by_client_record_year(client_record.id, tax_year)
        if report and report.status in _PRE_SUBMISSION_STATUSES:
            self.report_repo.update(report.id, tax_due=None, refund_due=None)


__all__ = ["AnnualReportFinancialService"]
