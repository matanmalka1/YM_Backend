from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.annual_reports.models.annual_report_model import AnnualReport
from app.utils.time_utils import utcnow


class AnnualReportDetail(Base):
    """
    Supplementary detail record for an annual report (1:1 with AnnualReport).

    Metadata columns only. Derived credit-point values are sourced directly from
    AnnualReportCreditPoint rows and are not persisted here.

    METADATA columns (client_approved_at, internal_notes, amendment_reason,
    pension_contribution, donation_amount, other_credits):
        Real business events written directly by service operations.
        Written ONLY via AnnualReportDetailRepository.update_meta().
    """

    __tablename__ = "annual_report_details"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("annual_reports.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    report: Mapped[AnnualReport] = relationship(
        "AnnualReport", back_populates="detail", uselist=False
    )

    # ── Deductions ────────────────────────────────────────────────────────
    pension_contribution: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    donation_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    other_credits: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    # ── Client approval ───────────────────────────────────────────────────
    client_approved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # ── Internal notes ────────────────────────────────────────────────────
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    amendment_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    def __repr__(self):
        return f"<AnnualReportDetail(id={self.id}, report_id={self.report_id})>"
