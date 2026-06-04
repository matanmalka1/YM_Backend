"""Repository for AnnualReportExpenseLine entities."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_expense_line import (
    AnnualReportExpenseLine,
    ExpenseCategoryType,
)


class AnnualReportExpenseRepository:
    _UPDATABLE_FIELDS = {
        "category",
        "amount",
        "recognition_rate",
        "description",
        "external_document_reference",
        "supporting_document_id",
    }

    def __init__(self, db: Session):
        self.db = db

    def create_for_report(
        self,
        annual_report_id: int,
        category: ExpenseCategoryType,
        amount: Decimal,
        recognition_rate: Decimal,
        description: str | None = None,
        external_document_reference: str | None = None,
        supporting_document_id: int | None = None,
    ) -> AnnualReportExpenseLine:
        line = AnnualReportExpenseLine(
            annual_report_id=annual_report_id,
            category=category,
            amount=amount,
            recognition_rate=recognition_rate,
            external_document_reference=external_document_reference,
            supporting_document_id=supporting_document_id,
            description=description,
        )
        self.db.add(line)
        self.db.flush()
        return line

    def list_by_report(self, annual_report_id: int) -> list[AnnualReportExpenseLine]:
        return self.db.scalars(
            select(AnnualReportExpenseLine)
            .where(AnnualReportExpenseLine.annual_report_id == annual_report_id)
            .order_by(AnnualReportExpenseLine.category.asc())
        ).all()

    def get_by_report_and_line_id(
        self, annual_report_id: int, line_id: int
    ) -> AnnualReportExpenseLine | None:
        return self.db.scalars(
            select(AnnualReportExpenseLine).where(
                AnnualReportExpenseLine.id == line_id,
                AnnualReportExpenseLine.annual_report_id == annual_report_id,
            )
        ).first()

    def apply_updates(
        self, line: AnnualReportExpenseLine, fields: dict[str, Any]
    ) -> AnnualReportExpenseLine:
        for k, v in fields.items():
            if k not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Unsupported expense line update field: {k}")
            setattr(line, k, v)
        self.db.flush()
        return line

    def delete_line(self, line: AnnualReportExpenseLine) -> None:
        self.db.delete(line)
        self.db.flush()

    def total_expenses(self, annual_report_id: int) -> Decimal:
        """Sum of gross (unrecognized) expense amounts."""
        result = self.db.scalar(
            select(func.coalesce(func.sum(AnnualReportExpenseLine.amount), 0)).where(
                AnnualReportExpenseLine.annual_report_id == annual_report_id
            )
        )
        return Decimal(str(result))

    def total_recognized_expenses(self, annual_report_id: int) -> Decimal:
        """Sum of amount × recognition_rate across all expense lines."""
        lines = self.list_by_report(annual_report_id)
        return sum(
            (Decimal(str(line.amount)) * Decimal(str(line.recognition_rate)) for line in lines),
            Decimal("0"),
        )


__all__ = ["AnnualReportExpenseRepository"]
