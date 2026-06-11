"""Income line items for an annual tax report."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class IncomeSourceType(str, PyEnum):
    BUSINESS = "business"  # הכנסות עסק / עצמאי
    SALARY = "salary"  # משכורת / שכר עבודה
    INTEREST = "interest"  # ריבית
    DIVIDENDS = "dividends"  # דיבידנד
    CAPITAL_GAINS = "capital_gains"  # רווחי הון
    RENTAL = "rental"  # שכירות
    FOREIGN = "foreign"  # הכנסות מחו"ל
    PENSION = "pension"  # פנסיה / קצבה
    OTHER = "other"  # אחר


class AnnualReportIncomeLine(Base):
    """
    Single income line attached to an annual report.

    One report may have multiple income lines of different source types.
    """

    __tablename__ = "annual_report_income_lines"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_annual_report_income_lines_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    annual_report_id: Mapped[int] = mapped_column(
        ForeignKey("annual_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[IncomeSourceType] = mapped_column(pg_enum(IncomeSourceType), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    def __repr__(self):
        return (
            f"<AnnualReportIncomeLine(id={self.id}, report_id={self.annual_report_id}, "
            f"type={self.source_type}, amount={self.amount})>"
        )


__all__ = ["AnnualReportIncomeLine", "IncomeSourceType"]
