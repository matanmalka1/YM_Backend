"""
VAT Invoice line-item ORM model.

Represents a single tax document (invoice, receipt, credit note, etc.)
attached to a VatWorkItem.

Design decisions:
- Amounts are always positive; credit notes are identified by document_type.
- invoice_date is Date (not DateTime) — VAT reporting is calendar-date based.
- No line-item breakdown — header-level totals sufficient for tax advisory work.
- counterparty_id_type enables validation routing (IL checksum vs. foreign).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.time_utils import utcnow

if TYPE_CHECKING:
    from app.vat.models.vat_work_item import VatWorkItem
from app.utils.enum_utils import pg_enum
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    InvoiceType,
    VatRateType,
)


class VatInvoice(Base):
    __tablename__ = "vat_invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    work_item_id: Mapped[int] = mapped_column(
        ForeignKey("vat_work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    work_item: Mapped[VatWorkItem] = relationship("VatWorkItem", back_populates="invoices")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Optional tag: which BusinessActivity (branch/shop/service) contributed this invoice.
    # NULL = untagged (valid — e.g. client has only one activity or is a COMPANY_LTD).
    business_activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )

    # Document classification
    invoice_type: Mapped[InvoiceType] = mapped_column(pg_enum(InvoiceType), nullable=False)
    document_type: Mapped[DocumentType | None] = mapped_column(
        pg_enum(DocumentType, name="vatdocumenttype"), nullable=True
    )
    # CREDIT_NOTE reversal is applied in service layer — amounts always positive here

    # Invoice identity
    invoice_number: Mapped[str] = mapped_column(String, nullable=False)
    invoice_date: Mapped[date] = mapped_column(nullable=False)  # Date only — no timezone issues

    # Counterparty
    counterparty_name: Mapped[str] = mapped_column(String, nullable=False)
    counterparty_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # מספר עוסק / ת"ז / דרכון
    counterparty_id_type: Mapped[CounterpartyIdType | None] = mapped_column(
        pg_enum(CounterpartyIdType), nullable=True
    )
    # Validation routing: IL_BUSINESS/IL_PERSONAL → checksum; FOREIGN → free text

    # Amounts — always positive; credit notes identified via document_type
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # VAT classification
    expense_category: Mapped[ExpenseCategory | None] = mapped_column(
        pg_enum(ExpenseCategory), nullable=True
    )
    rate_type: Mapped[VatRateType] = mapped_column(
        pg_enum(VatRateType), nullable=False, default=VatRateType.STANDARD
    )
    deduction_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("1.0000")
    )
    # Auto-populated from CATEGORY_DEDUCTION_RATES on create/update

    # Exceptional invoice flag (> 25,000 ₪ net — requires special handling)
    is_exceptional: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "work_item_id",
            "invoice_type",
            "invoice_number",
            name="uq_vat_invoice_item_type_number",
        ),
        Index("ix_vat_invoices_work_item_type", "work_item_id", "invoice_type"),
        Index("ix_vat_invoices_date", "invoice_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<VatInvoice(id={self.id}, work_item_id={self.work_item_id}, "
            f"type={self.invoice_type}, number={self.invoice_number})>"
        )
