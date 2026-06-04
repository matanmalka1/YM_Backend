"""VAT data auto-population for annual report income/expense lines.

Reads aggregated VAT invoice data for the report's business and tax year,
maps expense categories to annual report categories, and creates income/expense
lines in bulk. Existing lines are only replaced when force=True.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.annual_reports.domain.expense_rules import default_recognition_rate
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.repositories.report_repository import (
    AnnualReportReportRepository,
)
from app.annual_reports.services.messages import (
    ANNUAL_REPORT_NOT_FOUND,
    AUTOPOPULATE_INVALID_STATUS,
    AUTOPOPULATE_LINES_ALREADY_EXIST,
    VAT_IMPORTED_BUSINESS_INCOME_DESCRIPTION,
    VAT_IMPORTED_EXPENSE_DESCRIPTION,
)
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.vat_reports.repositories.vat_invoice_aggregation_repository import (
    VatInvoiceAggregationRepository,
)

# Statuses in which auto-population is permitted
_ALLOWED_STATUSES = {
    AnnualReportStatus.NOT_STARTED,
    AnnualReportStatus.COLLECTING_DOCS,
    AnnualReportStatus.IN_PREPARATION,
}

# Maps VAT ExpenseCategory values → annual report ExpenseCategoryType
_VAT_TO_ANNUAL: dict[str, ExpenseCategoryType] = {
    "inventory": ExpenseCategoryType.OTHER,
    "office": ExpenseCategoryType.OFFICE_RENT,
    "rent": ExpenseCategoryType.OFFICE_RENT,
    "professional_services": ExpenseCategoryType.PROFESSIONAL_SERVICES,
    "salary": ExpenseCategoryType.SALARIES,
    "marketing": ExpenseCategoryType.MARKETING,
    "vehicle": ExpenseCategoryType.VEHICLE,
    "fuel": ExpenseCategoryType.VEHICLE,
    "vehicle_maintenance": ExpenseCategoryType.VEHICLE,
    "vehicle_leasing": ExpenseCategoryType.VEHICLE,
    "tolls_and_parking": ExpenseCategoryType.VEHICLE,
    "vehicle_insurance": ExpenseCategoryType.INSURANCE,
    "insurance": ExpenseCategoryType.INSURANCE,
    "communication": ExpenseCategoryType.COMMUNICATION,
    "bank_fees": ExpenseCategoryType.BANK_FEES,
    "travel": ExpenseCategoryType.TRAVEL,
    "equipment": ExpenseCategoryType.OTHER,
    "maintenance": ExpenseCategoryType.OTHER,
    "utilities": ExpenseCategoryType.OTHER,
    "entertainment": ExpenseCategoryType.OTHER,
    "gifts": ExpenseCategoryType.OTHER,
    "municipal_tax": ExpenseCategoryType.OTHER,
    "postage_and_shipping": ExpenseCategoryType.OTHER,
    "mixed_expense": ExpenseCategoryType.OTHER,
    "other": ExpenseCategoryType.OTHER,
}


class VatImportService:
    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportReportRepository(db)
        self.income_repo = AnnualReportIncomeRepository(db)
        self.expense_repo = AnnualReportExpenseRepository(db)
        self.vat_agg_repo = VatInvoiceAggregationRepository(db)

    def auto_populate(self, report_id: int, force: bool = False) -> dict:
        """Import VAT income/expense data into annual report lines.

        Returns a summary dict with counts and totals.
        Raises ConflictError if lines already exist and force=False.
        """
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                "ANNUAL_REPORT.NOT_FOUND",
            )

        if report.status not in _ALLOWED_STATUSES:
            raise AppError(
                AUTOPOPULATE_INVALID_STATUS,
                "ANNUAL_REPORT.INVALID_STATUS_FOR_AUTOPOPULATE",
            )

        existing_income = self.income_repo.list_by_report(report_id)
        existing_expenses = self.expense_repo.list_by_report(report_id)
        lines_deleted = 0

        if (existing_income or existing_expenses) and not force:
            raise ConflictError(
                AUTOPOPULATE_LINES_ALREADY_EXIST,
                "ANNUAL_REPORT.LINES_ALREADY_EXIST",
            )

        if force:
            for line in existing_income:
                if self.income_repo.delete_for_report(report_id, line.id):
                    lines_deleted += 1
            for line in existing_expenses:
                if self.expense_repo.delete_for_report(report_id, line.id):
                    lines_deleted += 1

        income_total = self.vat_agg_repo.sum_income_net_by_client_year(
            report.client_record_id, report.tax_year
        )
        expense_by_vat_cat = self.vat_agg_repo.sum_expense_net_by_client_year_grouped(
            report.client_record_id, report.tax_year
        )

        income_lines_created = 0
        if income_total > 0:
            self.income_repo.add_line(
                report_id,
                IncomeSourceType.BUSINESS,
                income_total,
                VAT_IMPORTED_BUSINESS_INCOME_DESCRIPTION,
            )
            income_lines_created = 1

        # Merge VAT categories into annual report categories
        merged: dict[ExpenseCategoryType, Decimal] = {}
        for vat_cat, amount in expense_by_vat_cat.items():
            annual_cat = _VAT_TO_ANNUAL.get(vat_cat, ExpenseCategoryType.OTHER)
            merged[annual_cat] = merged.get(annual_cat, Decimal("0")) + Decimal(str(amount))

        expense_lines_created = 0
        expense_total = Decimal("0")
        for cat, total in merged.items():
            if total <= 0:
                continue
            self.expense_repo.add_line(
                annual_report_id=report_id,
                category=cat,
                amount=total,
                recognition_rate=default_recognition_rate(cat),
                description=VAT_IMPORTED_EXPENSE_DESCRIPTION.format(category=cat.value),
            )
            expense_lines_created += 1
            expense_total += total

        return {
            "annual_report_id": report_id,
            "income_lines_created": income_lines_created,
            "expense_lines_created": expense_lines_created,
            "income_total": float(income_total),
            "expense_total": float(expense_total),
            "lines_deleted": lines_deleted,
        }
