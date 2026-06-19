"""
VAT Work Item ORM model.

Tracks the full lifecycle of a client's VAT reporting period:
  PENDING_MATERIALS → MATERIAL_RECEIVED → DATA_ENTRY_IN_PROGRESS
  → READY_FOR_REVIEW → FILED

Once FILED the period is immutable — no invoices may be added or edited.

Israeli context:
  VAT (מע"מ) is reported monthly or bi-monthly to the Israel Tax Authority.
  Output VAT (מע"מ עסקאות) minus Input VAT (מע"מ תשומות) = Net VAT payable.

  Fields 87/66 in the VAT return correspond to total_output_net/total_input_net.
  These are snapshotted at filing time and must not change post-submission.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import SubmissionMethod, VatType
from app.database import Base

if TYPE_CHECKING:
    from app.vat.models.vat_invoice import VatInvoice
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow
from app.vat.models.vat_enums import VatWorkItemStatus


class VatWorkItem(Base):
    __tablename__ = "vat_work_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Period identity
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    period_type: Mapped[VatType] = mapped_column(
        pg_enum(VatType), nullable=False
    )  # snapshot at creation — immutable

    # Status lifecycle
    status: Mapped[VatWorkItemStatus] = mapped_column(
        pg_enum(VatWorkItemStatus),
        nullable=False,
        default=VatWorkItemStatus.MATERIAL_RECEIVED,
    )
    pending_materials_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Denormalized VAT totals (refreshed on every invoice mutation)
    total_output_vat: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_input_vat: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    net_vat: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )

    # Denormalized net totals — fields 87/66 in VAT return
    # Snapshotted at filing; do not recalculate post-FILED
    total_output_net: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    total_input_net: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )

    # Filing details (set when status → FILED)
    final_vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_overridden: Mapped[bool] = mapped_column(nullable=False, default=False)
    override_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_method: Mapped[SubmissionMethod | None] = mapped_column(
        pg_enum(SubmissionMethod), nullable=True
    )
    filed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    filed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submission_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Amendment tracking
    is_amendment: Mapped[bool] = mapped_column(nullable=False, default=False)
    amends_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("vat_work_items.id"), nullable=True
    )

    # Cross-domain link to regulatory calendar fact
    tax_calendar_entry_id: Mapped[int] = mapped_column(
        ForeignKey("tax_calendar_entries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    due_date_original: Mapped[date | None] = mapped_column(nullable=True)
    due_date_effective: Mapped[date | None] = mapped_column(nullable=True)
    due_date_override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow, onupdate=utcnow)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    invoices: Mapped[list[VatInvoice]] = relationship(
        "VatInvoice",
        back_populates="work_item",
        cascade="all, delete-orphan",
    )
    original_item: Mapped[VatWorkItem | None] = relationship(
        "VatWorkItem",
        foreign_keys="[VatWorkItem.amends_item_id]",
        remote_side="VatWorkItem.id",
        uselist=False,
    )

    __table_args__ = (
        Index(
            "uq_vat_work_item_client_record_period",
            "client_record_id",
            "period",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_vat_work_items_status", "status"),
        Index("ix_vat_work_items_period", "period"),
        Index(
            "idx_vat_work_items_calendar_entry_active",
            "tax_calendar_entry_id",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_vat_work_items_turnover_lookup",
            "client_record_id",
            "period",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_vat_work_items_active_due_client",
            "due_date_effective",
            "client_record_id",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<VatWorkItem(id={self.id}, client_record_id={self.client_record_id}, "
            f"period={self.period}, status={self.status})>"
        )


import_module("app.vat.models.vat_due_date_snapshot_events")
