"""VAT data auto-population for annual report income/expense lines.

Reads aggregated VAT invoice data for the report's client_record_id and tax year,
maps expense categories to annual report categories, and creates income/expense
lines in bulk. Existing lines are only replaced when force=True.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.annual_reports.annual_report_financial_line_helpers import (
    assert_client_allows_financial_mutation,
    expense_line_snapshot,
    income_line_snapshot,
)
from app.annual_reports.annual_report_messages import (
    ANNUAL_REPORT_NOT_FOUND,
    AUTOPOPULATE_AUDIT_ACTOR_REQUIRED,
    AUTOPOPULATE_INVALID_STATUS,
    AUTOPOPULATE_LINES_ALREADY_EXIST,
    EXPENSE_CATEGORY_LABELS,
    VAT_IMPORTED_BUSINESS_INCOME_DESCRIPTION,
    VAT_IMPORTED_EXPENSE_DESCRIPTION,
)
from app.annual_reports.domain.expense_rules import default_recognition_rate
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_expense_line import ExpenseCategoryType
from app.annual_reports.models.annual_report_income_line import IncomeSourceType
from app.annual_reports.repositories.annual_report_expense_repository import (
    AnnualReportExpenseRepository,
)
from app.annual_reports.repositories.annual_report_income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.repositories.annual_report_report_repository import (
    AnnualReportRootRepository,
)
from app.audit.audit_constants import (
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.vat.repositories.vat_invoice_aggregation_repository import (
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

_VAT_IMPORT_SOURCE = "vat_import"


def _decimal_amount(value) -> Decimal:
    return Decimal(str(value))


def _skipped_item(
    *,
    item_type: str,
    source: str,
    amount: Decimal,
    reason: str,
    annual_category: str | None = None,
) -> dict:
    return {
        "item_type": item_type,
        "source": source,
        "amount": amount,
        "reason": reason,
        "annual_category": annual_category,
    }


def _amount_strings(amounts: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in amounts.items()}


class VatImportService:
    def __init__(self, db: Session):
        self.db = db
        self.report_repo = AnnualReportRootRepository(db)
        self.income_repo = AnnualReportIncomeRepository(db)
        self.expense_repo = AnnualReportExpenseRepository(db)
        self.vat_agg_repo = VatInvoiceAggregationRepository(db)

    def auto_populate(
        self,
        report_id: int,
        force: bool = False,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> dict:
        """Import VAT income/expense data into annual report lines.

        Returns a summary dict with counts and totals.
        Raises ConflictError if lines already exist and force=False.
        """
        if actor_id is None:
            raise AppError(
                AUTOPOPULATE_AUDIT_ACTOR_REQUIRED,
                ErrorCode.ANNUAL_REPORT_AUDIT_ACTOR_REQUIRED,
            )

        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )

        assert_client_allows_financial_mutation(self.db, report.client_record_id)

        if report.status not in _ALLOWED_STATUSES:
            raise AppError(
                AUTOPOPULATE_INVALID_STATUS,
                ErrorCode.ANNUAL_REPORT_INVALID_STATUS_FOR_AUTOPOPULATE,
            )

        existing_income = self.income_repo.list_by_report(report_id)
        existing_expenses = self.expense_repo.list_by_report(report_id)
        lines_deleted = 0
        audit = EntityAuditWriter(self.db)

        if (existing_income or existing_expenses) and not force:
            raise ConflictError(
                AUTOPOPULATE_LINES_ALREADY_EXIST,
                ErrorCode.ANNUAL_REPORT_LINES_ALREADY_EXIST,
            )

        if force:
            for line in existing_income:
                old_value = income_line_snapshot(line) | {
                    "mutation_source": _VAT_IMPORT_SOURCE,
                    "mutation_reason": "force_replace",
                }
                self.income_repo.delete_line(line)
                lines_deleted += 1
                audit.append(
                    entity_type=ENTITY_ANNUAL_REPORT,
                    entity_id=report_id,
                    actor_id=actor_id,
                    actor_display_name=actor_name,
                    action=ACTION_INCOME_DELETED,
                    old_value=old_value,
                    note=(
                        f"mutation_source={_VAT_IMPORT_SOURCE}; "
                        f"reason=force_replace; line_id={line.id}"
                    ),
                )
            for line in existing_expenses:
                old_value = expense_line_snapshot(line) | {
                    "mutation_source": _VAT_IMPORT_SOURCE,
                    "mutation_reason": "force_replace",
                }
                self.expense_repo.delete_line(line)
                lines_deleted += 1
                audit.append(
                    entity_type=ENTITY_ANNUAL_REPORT,
                    entity_id=report_id,
                    actor_id=actor_id,
                    actor_display_name=actor_name,
                    action=ACTION_EXPENSE_DELETED,
                    old_value=old_value,
                    note=(
                        f"mutation_source={_VAT_IMPORT_SOURCE}; "
                        f"reason=force_replace; line_id={line.id}"
                    ),
                )

        income_total = _decimal_amount(
            self.vat_agg_repo.sum_income_net_by_client_year(
                report.client_record_id, report.tax_year
            )
        )
        expense_by_vat_cat = {
            vat_cat: _decimal_amount(amount)
            for vat_cat, amount in self.vat_agg_repo.sum_expense_net_by_client_year_grouped(
                report.client_record_id, report.tax_year
            ).items()
        }

        skipped_items: list[dict] = []
        warnings: list[str] = []

        income_lines_created = 0
        if income_total > 0:
            line = self.income_repo.create_for_report(
                report_id,
                IncomeSourceType.BUSINESS,
                income_total,
                VAT_IMPORTED_BUSINESS_INCOME_DESCRIPTION,
            )
            income_lines_created = 1
            audit.append(
                entity_type=ENTITY_ANNUAL_REPORT,
                entity_id=report_id,
                actor_id=actor_id,
                actor_display_name=actor_name,
                action=ACTION_INCOME_ADDED,
                new_value=income_line_snapshot(line)
                | {
                    "source": _VAT_IMPORT_SOURCE,
                    "source_total": str(income_total),
                },
                note=f"source={_VAT_IMPORT_SOURCE}",
            )
        elif income_total < 0:
            skipped_items.append(
                _skipped_item(
                    item_type="income",
                    source="business",
                    amount=income_total,
                    reason="negative_total",
                )
            )
            warnings.append(
                "VAT import skipped negative business income total; review credit notes or corrections."
            )

        merged: dict[ExpenseCategoryType, Decimal] = {}
        source_breakdown: dict[ExpenseCategoryType, dict[str, Decimal]] = {}
        for vat_cat, amount in expense_by_vat_cat.items():
            annual_cat = _VAT_TO_ANNUAL.get(vat_cat, ExpenseCategoryType.OTHER)
            merged[annual_cat] = merged.get(annual_cat, Decimal("0")) + amount
            category_breakdown = source_breakdown.setdefault(annual_cat, {})
            category_breakdown[vat_cat] = category_breakdown.get(vat_cat, Decimal("0")) + amount

        expense_lines_created = 0
        expense_total = Decimal("0")
        expense_breakdown: list[dict] = []
        for cat, total in merged.items():
            breakdown = source_breakdown.get(cat, {})
            for vat_cat, amount in breakdown.items():
                if total > 0 and amount < 0:
                    skipped_items.append(
                        _skipped_item(
                            item_type="expense",
                            source=vat_cat,
                            amount=amount,
                            reason="negative_source_contribution",
                            annual_category=cat.value,
                        )
                    )
                    warnings.append(
                        "VAT import included negative source category "
                        f"{vat_cat} under {cat.value}; review credits or corrections."
                    )
            expense_breakdown.append(
                {
                    "annual_category": cat.value,
                    "amount": total,
                    "source_vat_categories": breakdown,
                }
            )
            if total < 0:
                skipped_items.append(
                    _skipped_item(
                        item_type="expense",
                        source="merged_vat_categories",
                        amount=total,
                        reason="negative_total",
                        annual_category=cat.value,
                    )
                )
                warnings.append(
                    "VAT import skipped negative expense total for "
                    f"{cat.value}; review credit notes or corrections."
                )
                continue
            if total == 0:
                skipped_items.append(
                    _skipped_item(
                        item_type="expense",
                        source="merged_vat_categories",
                        amount=total,
                        reason="zero_total",
                        annual_category=cat.value,
                    )
                )
                continue
            line = self.expense_repo.create_for_report(
                annual_report_id=report_id,
                category=cat,
                amount=total,
                recognition_rate=default_recognition_rate(cat),
                description=VAT_IMPORTED_EXPENSE_DESCRIPTION.format(
                    category_label=EXPENSE_CATEGORY_LABELS.get(cat.value, cat.value)
                ),
            )
            expense_lines_created += 1
            expense_total += total
            audit.append(
                entity_type=ENTITY_ANNUAL_REPORT,
                entity_id=report_id,
                actor_id=actor_id,
                actor_display_name=actor_name,
                action=ACTION_EXPENSE_ADDED,
                new_value=expense_line_snapshot(line)
                | {
                    "source": _VAT_IMPORT_SOURCE,
                    "source_vat_categories": _amount_strings(breakdown),
                },
                note=f"source={_VAT_IMPORT_SOURCE}",
            )

        return {
            "annual_report_id": report_id,
            "income_lines_created": income_lines_created,
            "expense_lines_created": expense_lines_created,
            "income_total": income_total if income_total > 0 else Decimal("0"),
            "expense_total": expense_total,
            "lines_deleted": lines_deleted,
            "skipped_items": skipped_items,
            "warnings": warnings,
            "expense_breakdown": expense_breakdown,
        }
