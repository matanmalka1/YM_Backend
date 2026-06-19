"""Annual report income and expense line mutation service."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.annual_reports.domain.expense_rules import default_recognition_rate
from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.repositories.annual_report_expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.annual_report_income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.schemas.annual_report_financials import (
    ExpenseLineResponse,
    IncomeLineResponse,
)
from app.annual_reports.annual_report_financial_line_helpers import (
    assert_client_allows_financial_mutation,
    audit_scalar,
    expense_line_snapshot,
    income_line_snapshot,
)
from app.annual_reports.annual_report_messages import (
    ANNUAL_REPORT_NOT_FOUND,
    EXPENSE_LINE_NOT_FOUND,
    INCOME_LINE_NOT_FOUND,
    INVALID_EXPENSE_CATEGORY_ERROR,
    INVALID_INCOME_SOURCE_ERROR,
)
from app.annual_reports.services.annual_report_tax_service import AnnualReportTaxService
from app.audit.audit_constants import (
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.services.audit_entity_audit_writer import EntityAuditWriter
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError


class AnnualReportFinancialLineService:
    """Create, update, and delete annual-report income and expense lines."""

    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportRepository(db)
        self.income_repo = AnnualReportIncomeRepository(db)
        self.expense_repo = AnnualReportExpenseRepository(db)

    def _get_report_or_raise(self, report_id: int):
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return report

    def _invalidate_tax_for_report(self, report) -> None:
        AnnualReportTaxService(self.db).invalidate_tax_if_open(
            report.client_record_id,
            report.tax_year,
        )

    def add_income(
        self,
        report_id: int,
        source_type: str,
        amount: Decimal,
        description: str | None = None,
        actor_id: int | None = None,
    ) -> IncomeLineResponse:
        report = self._get_report_or_raise(report_id)
        assert_client_allows_financial_mutation(self.db, report.client_record_id)
        valid_sources = {e.value for e in IncomeSourceType}
        if source_type not in valid_sources:
            raise AppError(
                INVALID_INCOME_SOURCE_ERROR.format(source_type=source_type),
                ErrorCode.ANNUAL_REPORT_INVALID_TYPE,
            )
        line = self.income_repo.create_for_report(
            report_id, IncomeSourceType(source_type), amount, description
        )
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_INCOME_ADDED,
            new_value=income_line_snapshot(line),
        )
        self._invalidate_tax_for_report(report)
        return IncomeLineResponse.model_validate(line)

    def update_income(
        self, report_id: int, line_id: int, actor_id: int | None = None, **fields
    ) -> IncomeLineResponse:
        report = self._get_report_or_raise(report_id)
        assert_client_allows_financial_mutation(self.db, report.client_record_id)
        if "source_type" in fields and fields["source_type"] is not None:
            valid_sources = {e.value for e in IncomeSourceType}
            if fields["source_type"] not in valid_sources:
                raise AppError(
                    INVALID_INCOME_SOURCE_ERROR.format(source_type=fields["source_type"]),
                    ErrorCode.ANNUAL_REPORT_INVALID_TYPE,
                )
            fields["source_type"] = IncomeSourceType(fields["source_type"])
        # `fields` already contains only client-sent keys (exclude_unset). Pass
        # them through directly so an explicit null clears a nullable field; the
        # request schema rejects null for non-nullable fields.
        update_fields = fields
        line = self.income_repo.get_by_report_and_line_id(report_id, line_id)
        if not line:
            raise NotFoundError(
                INCOME_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        if not update_fields:
            return IncomeLineResponse.model_validate(line)
        old_value = income_line_snapshot(line)
        line = self.income_repo.apply_updates(line, update_fields)
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_INCOME_UPDATED,
            old_value=old_value,
            new_value={k: audit_scalar(k, v) for k, v in update_fields.items()},
        )
        self._invalidate_tax_for_report(report)
        return IncomeLineResponse.model_validate(line)

    def delete_income(self, report_id: int, line_id: int, actor_id: int | None = None) -> None:
        report = self._get_report_or_raise(report_id)
        assert_client_allows_financial_mutation(self.db, report.client_record_id)
        line = self.income_repo.get_by_report_and_line_id(report_id, line_id)
        if not line:
            raise NotFoundError(
                INCOME_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        old_value = income_line_snapshot(line)
        self.income_repo.delete_line(line)
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_INCOME_DELETED,
            old_value=old_value,
            note=f"line_id={line_id}",
        )
        self._invalidate_tax_for_report(report)

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
        assert_client_allows_financial_mutation(self.db, report.client_record_id)
        valid_categories = {e.value for e in ExpenseCategoryType}
        if category not in valid_categories:
            raise AppError(
                INVALID_EXPENSE_CATEGORY_ERROR.format(category=category),
                ErrorCode.ANNUAL_REPORT_INVALID_TYPE,
            )
        expense_category = ExpenseCategoryType(category)
        rate = (
            recognition_rate
            if recognition_rate is not None
            else default_recognition_rate(expense_category)
        )
        line = self.expense_repo.create_for_report(
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
            new_value=expense_line_snapshot(line),
        )
        self._invalidate_tax_for_report(report)
        return ExpenseLineResponse.model_validate(line)

    def update_expense(
        self, report_id: int, line_id: int, actor_id: int | None = None, **fields
    ) -> ExpenseLineResponse:
        report = self._get_report_or_raise(report_id)
        assert_client_allows_financial_mutation(self.db, report.client_record_id)
        if "category" in fields and fields["category"] is not None:
            valid_categories = {e.value for e in ExpenseCategoryType}
            if fields["category"] not in valid_categories:
                raise AppError(
                    INVALID_EXPENSE_CATEGORY_ERROR.format(category=fields["category"]),
                    ErrorCode.ANNUAL_REPORT_INVALID_TYPE,
                )
            fields["category"] = ExpenseCategoryType(fields["category"])
        # `fields` already contains only client-sent keys (exclude_unset). Pass
        # them through directly so an explicit null clears a nullable field; the
        # request schema rejects null for non-nullable fields.
        update_fields = fields
        line = self.expense_repo.get_by_report_and_line_id(report_id, line_id)
        if not line:
            raise NotFoundError(
                EXPENSE_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        if not update_fields:
            return ExpenseLineResponse.model_validate(line)
        old_value = expense_line_snapshot(line)
        line = self.expense_repo.apply_updates(line, update_fields)
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_EXPENSE_UPDATED,
            old_value=old_value,
            new_value={k: audit_scalar(k, v) for k, v in update_fields.items()},
        )
        self._invalidate_tax_for_report(report)
        return ExpenseLineResponse.model_validate(line)

    def delete_expense(self, report_id: int, line_id: int, actor_id: int | None = None) -> None:
        report = self._get_report_or_raise(report_id)
        assert_client_allows_financial_mutation(self.db, report.client_record_id)
        line = self.expense_repo.get_by_report_and_line_id(report_id, line_id)
        if not line:
            raise NotFoundError(
                EXPENSE_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        old_value = expense_line_snapshot(line)
        self.expense_repo.delete_line(line)
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=ACTION_EXPENSE_DELETED,
            old_value=old_value,
            note=f"line_id={line_id}",
        )
        self._invalidate_tax_for_report(report)


__all__ = ["AnnualReportFinancialLineService"]
