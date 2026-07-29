"""Advance payment model for Israeli tax prepayments.

An ``AdvancePayment`` represents a client tax prepayment (``מקדמה``) for a
given reporting period.

Context:
    Reporting legal entities pay advance payments (``מקדמות``) to the Israeli

    Tax Authority monthly or bi-monthly, based on a configured advance rate.
    based on a percentage of prior-year income.
    The expected amount is derived: turnover_amount × advance_rate / 100 =
    calculated_amount (always gross). withheld_amount (ניכוי במקור) is then
    subtracted to produce expected_amount, floored at zero. override_amount
    replaces the final expected_amount when set, ignoring withheld_amount.

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

from app.common.enums import ObligationStatus
from app.common.soft_delete import SoftDeletableMixin
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


def paid_in_full_expr():
    """SQL twin of :meth:`AdvancePayment.is_paid_in_full` — money, not lifecycle.

    These were the same question while the status was derived from the amounts:
    ``status == PAID`` *meant* ``paid_amount >= expected_amount``. They stop being
    the same question once the status is a real lifecycle. An advisor may close a
    period that was underpaid — the difference is a debt, not an open period — and
    a period paid in full is not closed until someone confirms it was reported.

    Collection and reporting KPIs ask this one. The work queue, the tax calendar
    and anything asking "is this obligation done" ask the lifecycle one.
    """
    return (AdvancePayment.expected_amount > 0) & (
        AdvancePayment.paid_amount >= AdvancePayment.expected_amount
    )


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
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

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
    # Withheld-at-source credit (ניכוי במקור), subtracted from calculated_amount
    # to derive expected_amount. NULL means "none entered", treated as zero.
    withheld_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Provenance of turnover_amount. turnover_source is NULL exactly when
    # turnover_amount is NULL. turnover_snapshot_at is additionally NULL on rows
    # backfilled by migration 8a1c47d0b3e2, whose snapshot time is unknowable.
    turnover_source: Mapped[TurnoverSource | None] = mapped_column(
        pg_enum(TurnoverSource), nullable=True
    )
    turnover_snapshot_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # ── Status & payment ──────────────────────────────────────────────────────
    status: Mapped[ObligationStatus] = mapped_column(
        pg_enum(ObligationStatus),
        default=ObligationStatus.AWAITING_INPUT,
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        pg_enum(PaymentMethod), nullable=True
    )
    # Bank/authority reference (אסמכתה) of the payment, as reported by the client.
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Closing facts (set when status → SUBMITTED) ───────────────────────────
    # paid_at is the payment event; closed_at is the closing act — they differ
    # when an advisor settles a part-paid or unpaid period (D-16).
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # NULL means "no due date at close" (D-32), never "unknown" — written once, at the close
    closed_late: Mapped[bool | None] = mapped_column(nullable=True)

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
        ),
        Index("idx_advance_payment_client_record_period", "client_record_id", "period"),
        Index(
            "idx_advance_payment_period_active",
            "period",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_advance_payment_status", "status"),
        Index("idx_advance_payment_due_date", "due_date"),
        Index(
            "idx_advance_payment_calendar_entry_active",
            "tax_calendar_entry_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    @property
    def is_paid_in_full(self) -> bool:
        """Money, not lifecycle. See :func:`paid_in_full_expr`."""
        return self.expected_amount > 0 and self.paid_amount >= self.expected_amount

    @property
    def outstanding_amount(self) -> Decimal:
        """What is still owed. A part-paid advance is in progress with a balance,
        which is what `partial` was really describing — a fact about the amount,
        not a stage of the lifecycle."""
        return max(Decimal("0.00"), self.expected_amount - self.paid_amount)

    def __repr__(self):
        return (
            f"<AdvancePayment(id={self.id}, client_record_id={self.client_record_id}, "
            f"period='{self.period}', status='{self.status}')>"
        )


import_module("app.advance_payments.models.advance_payment_due_date_snapshot_events")
