"""Repository for VatInvoice CRUD operations.

Aggregation queries (sum_vat_both_types, sum_net_both_types,
sum_income_net_by_client_year) live in VatInvoiceAggregationRepository.
This class re-exposes them via composition for backward compatibility.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    InvoiceType,
    VatRateType,
)
from app.vat.models.vat_invoice import VatInvoice
from app.vat.repositories.vat_invoice_aggregation_repository import (
    VatInvoiceAggregationRepository,
)


class VatInvoiceRepository(BaseRepository[VatInvoice]):
    model = VatInvoice

    def __init__(self, db: Session):
        super().__init__(db)
        self._agg = VatInvoiceAggregationRepository(db)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(
        self,
        work_item_id: int,
        created_by: int,
        invoice_type: InvoiceType,
        invoice_number: str,
        invoice_date: date,
        counterparty_name: str,
        net_amount: float,
        vat_amount: float,
        counterparty_id: str | None = None,
        counterparty_id_type: CounterpartyIdType | None = None,
        expense_category: ExpenseCategory | None = None,
        rate_type: VatRateType = VatRateType.STANDARD,
        deduction_rate: float = 1.0,
        document_type: DocumentType | None = None,
        is_exceptional: bool = False,
        business_activity_id: int | None = None,
    ) -> VatInvoice:
        return self.build_and_add(
            work_item_id=work_item_id,
            created_by=created_by,
            invoice_type=invoice_type,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            counterparty_name=counterparty_name,
            counterparty_id=counterparty_id,
            counterparty_id_type=counterparty_id_type,
            net_amount=net_amount,
            vat_amount=vat_amount,
            expense_category=expense_category,
            rate_type=rate_type,
            deduction_rate=deduction_rate,
            document_type=document_type,
            is_exceptional=is_exceptional,
            business_activity_id=business_activity_id,
        )

    def get_by_number(
        self, work_item_id: int, invoice_type: InvoiceType, invoice_number: str
    ) -> VatInvoice | None:
        return self.db.scalars(
            select(VatInvoice).where(
                VatInvoice.work_item_id == work_item_id,
                VatInvoice.invoice_type == invoice_type,
                VatInvoice.invoice_number == invoice_number,
            )
        ).first()

    def list_by_work_item(
        self,
        work_item_id: int,
        invoice_type: InvoiceType | None = None,
    ) -> list[VatInvoice]:
        stmt = select(VatInvoice).where(VatInvoice.work_item_id == work_item_id)
        if invoice_type:
            stmt = stmt.where(VatInvoice.invoice_type == invoice_type)
        return self.db.scalars(stmt.order_by(VatInvoice.invoice_date.asc())).all()

    def update(self, entity_id: int, **fields) -> VatInvoice | None:
        invoice = self.get_by_id(entity_id)
        if not invoice:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(invoice, key, value)
        self.db.flush()
        return invoice

    # ── Aggregation (delegated) ───────────────────────────────────────────────

    def sum_vat_both_types(self, work_item_id: int) -> tuple[float, float]:
        return self._agg.sum_vat_both_types(work_item_id)

    def sum_net_both_types(self, work_item_id: int) -> tuple[float, float]:
        return self._agg.sum_net_both_types(work_item_id)

    def sum_income_net_by_client_year(self, client_record_id: int, year: int) -> float:
        return self._agg.sum_income_net_by_client_year(client_record_id, year)

    def sum_expense_net_by_client_year_grouped(self, client_record_id: int, year: int) -> dict:
        return self._agg.sum_expense_net_by_client_year_grouped(client_record_id, year)
