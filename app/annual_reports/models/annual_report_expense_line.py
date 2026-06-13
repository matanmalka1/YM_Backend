"""Deductible expense line items for an annual tax report."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow

if TYPE_CHECKING:
    from app.documents.permanent_documents.models.permanent_document import PermanentDocument


class ExpenseCategoryType(str, PyEnum):
    """Annual report expense-line categories used for income-tax / reporting classification.

    These are higher-level recognition categories for the annual report, not
    the same as VAT's ExpenseCategory. VAT's 24 granular categories are
    consolidated into these 12 via _VAT_TO_ANNUAL in
    backend/app/annual_reports/services/vat_import_service.py.
    """

    OFFICE_RENT = "office_rent"  # שכירות משרד
    PROFESSIONAL_SERVICES = "professional_services"  # שירותים מקצועיים
    SALARIES = "salaries"  # שכר עבודה
    DEPRECIATION = "depreciation"  # פחת
    VEHICLE = "vehicle"  # רכב
    MARKETING = "marketing"  # שיווק ופרסום
    INSURANCE = "insurance"  # ביטוח
    COMMUNICATION = "communication"  # תקשורת
    TRAVEL = "travel"  # נסיעות
    TRAINING = "training"  # הכשרה מקצועית
    BANK_FEES = "bank_fees"  # עמלות בנק
    OTHER = "other"  # אחר


class AnnualReportExpenseLine(Base):
    """
    Single deductible expense line attached to an annual report.
    """

    __tablename__ = "annual_report_expense_lines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    annual_report_id: Mapped[int] = mapped_column(
        ForeignKey("annual_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[ExpenseCategoryType] = mapped_column(
        pg_enum(ExpenseCategoryType), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recognition_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("1.00")
    )
    external_document_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supporting_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("permanent_documents.id"), nullable=True, index=True
    )
    supporting_document: Mapped[PermanentDocument | None] = relationship(
        "PermanentDocument", lazy="select"
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    def __repr__(self):
        return (
            f"<AnnualReportExpenseLine(id={self.id}, report_id={self.annual_report_id}, "
            f"category={self.category}, amount={self.amount})>"
        )


__all__ = [
    "AnnualReportExpenseLine",
    "ExpenseCategoryType",
]
