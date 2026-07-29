"""Aggregation queries for VatInvoice entities."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_enums import DocumentType, InvoiceType, VatRateType
from app.vat.models.vat_invoice import VatInvoice
from app.vat.models.vat_work_item import VatWorkItem


@dataclass(frozen=True)
class VatExpenseCategoryBreakdown:
    category: str
    deduction_rate: Decimal
    net_amount: Decimal
    gross_vat: Decimal
    deductible_vat: Decimal


class VatInvoiceAggregationRepository(BaseRepository[VatInvoice]):
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _signed_amount(column):
        """Treat credit notes as negative contributions while stored values stay positive."""
        return case(
            (
                VatInvoice.document_type == DocumentType.CREDIT_NOTE,
                -column,
            ),
            else_=column,
        )

    def sum_vat_both_types(self, work_item_id: int) -> tuple[Decimal, Decimal]:
        """Return (output_vat, deductible_input_vat).

        - Output VAT: sum of vat_amount for INCOME invoices with STANDARD rate only
          (EXEMPT and ZERO_RATE contribute 0 to output VAT)
        - Input VAT: sum of vat_amount * deduction_rate for EXPENSE invoices
        """
        rows = self.db.execute(
            select(
                VatInvoice.invoice_type,
                func.sum(
                    case(
                        (
                            VatInvoice.invoice_type == InvoiceType.INCOME,
                            case(
                                (
                                    VatInvoice.rate_type == VatRateType.STANDARD,
                                    self._signed_amount(VatInvoice.vat_amount),
                                ),
                                else_=0,
                            ),
                        ),
                        (
                            VatInvoice.invoice_type == InvoiceType.EXPENSE,
                            self._signed_amount(VatInvoice.vat_amount) * VatInvoice.deduction_rate,
                        ),
                        else_=0,
                    )
                ).label("total"),
            )
            .where(
                VatInvoice.work_item_id == work_item_id,
                VatInvoice.invoice_type.in_((InvoiceType.INCOME, InvoiceType.EXPENSE)),
            )
            .group_by(VatInvoice.invoice_type)
        ).all()
        grouped = {row.invoice_type: Decimal(str(row.total or 0)) for row in rows}
        output_vat = grouped.get(InvoiceType.INCOME, Decimal("0"))
        input_vat = grouped.get(InvoiceType.EXPENSE, Decimal("0"))
        return output_vat, input_vat

    def sum_net_both_types(self, work_item_id: int) -> tuple[Decimal, Decimal]:
        """Return (output_net, input_net) — sum of net_amount for INCOME and EXPENSE."""
        rows = self.db.execute(
            select(
                VatInvoice.invoice_type,
                func.sum(self._signed_amount(VatInvoice.net_amount)).label("total"),
            )
            .where(
                VatInvoice.work_item_id == work_item_id,
                VatInvoice.invoice_type.in_((InvoiceType.INCOME, InvoiceType.EXPENSE)),
            )
            .group_by(VatInvoice.invoice_type)
        ).all()
        grouped = {row.invoice_type: Decimal(str(row.total or 0)) for row in rows}
        return (
            grouped.get(InvoiceType.INCOME, Decimal("0")),
            grouped.get(InvoiceType.EXPENSE, Decimal("0")),
        )

    def expense_breakdown(self, work_item_id: int) -> list[VatExpenseCategoryBreakdown]:
        """Return signed expense amounts grouped by category and its stored deduction rate.

        The deduction rate is part of the grouping key, not an aggregate: invoices in one
        category can carry different stored rates (the rate is resolved at write time), and
        collapsing them would make the displayed rate describe only some of the row's amounts.
        """
        rows = self.db.execute(
            select(
                VatInvoice.expense_category,
                VatInvoice.deduction_rate,
                func.sum(self._signed_amount(VatInvoice.net_amount)).label("net_amount"),
                func.sum(self._signed_amount(VatInvoice.vat_amount)).label("gross_vat"),
                func.sum(
                    self._signed_amount(VatInvoice.vat_amount) * VatInvoice.deduction_rate
                ).label("deductible_vat"),
            )
            .where(
                VatInvoice.work_item_id == work_item_id,
                VatInvoice.invoice_type == InvoiceType.EXPENSE,
            )
            .group_by(VatInvoice.expense_category, VatInvoice.deduction_rate)
            .order_by(VatInvoice.expense_category, VatInvoice.deduction_rate)
        ).all()
        return [
            VatExpenseCategoryBreakdown(
                category=row.expense_category.value if row.expense_category else "other",
                deduction_rate=Decimal(str(row.deduction_rate)),
                net_amount=Decimal(str(row.net_amount or 0)),
                gross_vat=Decimal(str(row.gross_vat or 0)),
                deductible_vat=Decimal(str(row.deductible_vat or 0)),
            )
            for row in rows
        ]

    def sum_income_net_by_client_year(self, client_record_id: int, year: int) -> Decimal:
        """Sum net_amount of INCOME invoices for a client across a tax year.

        Used for OSEK PATUR ceiling enforcement.
        """
        result = self.db.scalar(
            select(func.sum(self._signed_amount(VatInvoice.net_amount)))
            .join(VatWorkItem, VatInvoice.work_item_id == VatWorkItem.id)
            .where(
                VatWorkItem.client_record_id == client_record_id,
                VatInvoice.invoice_type == InvoiceType.INCOME,
                VatWorkItem.period.like(f"{year}-%"),
                VatWorkItem.deleted_at.is_(None),
                # An amendment is born holding a copy of every invoice, so an
                # amended period's invoices exist under two work items. Without
                # this, the ceiling check sees the period's income twice.
                VatWorkItem.chain_tip_clause(),
            )
        )
        return Decimal(str(result or 0))

    def sum_expense_net_by_client_year_grouped(
        self, client_record_id: int, year: int
    ) -> dict[str, Decimal]:
        """Return {expense_category_value: total_net_amount} for EXPENSE invoices.

        Aggregates across all work items for this client in the given tax year.
        Used by annual reports auto-population to map VAT expense categories.
        """
        rows = self.db.execute(
            select(
                VatInvoice.expense_category,
                func.sum(self._signed_amount(VatInvoice.net_amount)).label("total"),
            )
            .join(VatWorkItem, VatInvoice.work_item_id == VatWorkItem.id)
            .where(
                VatWorkItem.client_record_id == client_record_id,
                VatInvoice.invoice_type == InvoiceType.EXPENSE,
                VatWorkItem.period.like(f"{year}-%"),
                VatWorkItem.deleted_at.is_(None),
                VatWorkItem.chain_tip_clause(),
            )
            .group_by(VatInvoice.expense_category)
        ).all()
        return {
            (row.expense_category.value if row.expense_category else "other"): Decimal(
                str(row.total or 0)
            )
            for row in rows
        }
