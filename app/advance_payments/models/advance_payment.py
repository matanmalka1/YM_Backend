"""Advance payment model for Israeli tax prepayments.

An ``AdvancePayment`` represents a client tax prepayment (``מקדמה``) for a
given reporting period.

Context:
    Reporting legal entities pay advance payments (``מקדמות``) to the Israeli

    Tax Authority monthly or bi-monthly, based on a configured advance rate.
    based on a percentage of prior-year income.
    The expected amount is derived: turnover_amount × advance_rate / 100 =
    calculated_amount. override_amount replaces the final expected_amount when
    set.

Period handling:
    ``period`` follows the same ``YYYY-MM`` convention as ``VatWorkItem`` and
    stores the first month of the reporting period. ``period_months_count``
    distinguishes monthly (1) from bi-monthly (2) periods without duplicating
    period logic.

Design notes:
    - ``period`` and ``period_months_count`` are used instead of separate month
      and year fields for consistency with VAT handling.
    - ``turnover_amount`` is a frozen snapshot, never a live view of VAT. Once
      written it does not follow later amendments to the VAT return it came
      from, because the advance was paid against the figure known at the time.
      ``turnover_source`` and ``turnover_snapshot_at`` record where and when it
      was frozen.
    - ``paid_at`` stores the actual payment timestamp for auditability.
    - ``payment_method`` is an enum; direct debit is the most common option for
      advance payments.
    - Currency is always ILS by project convention, so no currency column is
      stored.
    - Soft deletion is enabled because this is a client-owned entity.
    - Uniqueness of (client_record_id, period) is enforced via a partial index
      (WHERE deleted_at IS NULL) — not a hard UniqueConstraint — so that a
      soft-deleted record never blocks recreation of the same period.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from importlib import import_module

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.soft_delete import SoftDeletableMixin
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class AdvancePaymentStatus(str, PyEnum):
    """Lifecycle status of an advance payment."""

    PENDING = "pending"  # Not yet paid
    PAID = "paid"  # Paid in full
    PARTIAL = "partial"  # Paid partially


class PaymentMethod(str, PyEnum):
    """Supported payment methods for an advance payment."""

    BANK_TRANSFER = "bank_transfer"  # Bank transfer
    CREDIT_CARD = "credit_card"  # Credit card
    CHECK = "check"  # Check
    DIRECT_DEBIT = "direct_debit"  # Direct debit — very common for advance payments
    CASH = "cash"  # Cash — rare, exists at post office bank
    OTHER = "other"


class TurnoverSource(str, PyEnum):
    """Where ``turnover_amount`` was snapshotted from."""

    MANUAL = "manual"  # Typed by an advisor
    VAT_FILED = "vat_filed"  # Snapshotted from a filed VAT return
    VAT_PENDING = "vat_pending"  # Snapshotted from a VAT return not yet filed


class AdvancePayment(SoftDeletableMixin, Base):
    """SQLAlchemy model for a client's advance tax payment record."""

    __tablename__ = "advance_payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )

    # ── Period ────────────────────────────────────────────────────────────────
    period: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # "YYYY-MM" — first month in period
    period_months_count: Mapped[int] = mapped_column(
        nullable=False, default=1
    )  # 1=monthly, 2=bi-monthly
    due_date: Mapped[date] = mapped_column(
        nullable=False
    )  # Usually the 15th of the month after the period
    due_date_original: Mapped[date | None] = mapped_column(nullable=True)
    due_date_effective: Mapped[date | None] = mapped_column(nullable=True)
    due_date_override_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Amounts ───────────────────────────────────────────────────────────────
    expected_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0"
    )

    # ── Calculation fields ────────────────────────────────────────────────────
    # turnover_amount and advance_rate are source snapshots — NULL means "unknown",
    # not zero. calculated_amount is a derived display value, NOT NULL.
    turnover_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    advance_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    calculated_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    override_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Provenance of turnover_amount. turnover_source is NULL exactly when
    # turnover_amount is NULL. turnover_snapshot_at is additionally NULL on rows
    # backfilled by migration 8a1c47d0b3e2, whose snapshot time is unknowable.
    turnover_source: Mapped[TurnoverSource | None] = mapped_column(
        pg_enum(TurnoverSource), nullable=True
    )
    turnover_snapshot_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # ── Status & payment ──────────────────────────────────────────────────────
    status: Mapped[AdvancePaymentStatus] = mapped_column(
        pg_enum(AdvancePaymentStatus),
        default=AdvancePaymentStatus.PENDING,
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        pg_enum(PaymentMethod), nullable=True
    )
    # Bank/authority reference (אסמכתה) of the payment, as reported by the client.
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Cross-domain links ────────────────────────────────────────────────────
    annual_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("annual_reports.id"), nullable=True, index=True
    )
    tax_calendar_entry_id: Mapped[int] = mapped_column(
        ForeignKey("tax_calendar_entries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    __table_args__ = (
        Index(
            "uq_advance_payment_client_record_period_active",
            "client_record_id",
            "period",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_advance_payment_client_record_period", "client_record_id", "period"),
        Index(
            "idx_advance_payment_period_active",
            "period",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_advance_payment_status", "status"),
        Index("idx_advance_payment_due_date", "due_date"),
        Index(
            "idx_advance_payment_calendar_entry_active",
            "tax_calendar_entry_id",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self):
        return (
            f"<AdvancePayment(id={self.id}, client_record_id={self.client_record_id}, "
            f"period='{self.period}', status='{self.status}')>"
        )


import_module("app.advance_payments.models.advance_payment_due_date_snapshot_events")
