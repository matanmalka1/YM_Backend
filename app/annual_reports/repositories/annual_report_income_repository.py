"""Repository for AnnualReportIncomeLine entities."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_income_line import (
    AnnualReportIncomeLine,
    IncomeSourceType,
)


class AnnualReportIncomeRepository:
    _UPDATABLE_FIELDS = {"source_type", "amount", "description"}

    def __init__(self, db: Session):
        self.db = db

    def create_for_report(
        self,
        annual_report_id: int,
        source_type: IncomeSourceType,
        amount: Decimal,
        description: str | None = None,
    ) -> AnnualReportIncomeLine:
        line = AnnualReportIncomeLine(
            annual_report_id=annual_report_id,
            source_type=source_type,
            amount=amount,
            description=description,
        )
        self.db.add(line)
        self.db.flush()
        return line

    def list_by_report(self, annual_report_id: int) -> list[AnnualReportIncomeLine]:
        return self.db.scalars(
            select(AnnualReportIncomeLine)
            .where(AnnualReportIncomeLine.annual_report_id == annual_report_id)
            .order_by(AnnualReportIncomeLine.source_type.asc())
        ).all()

    def get_by_report_and_line_id(
        self, annual_report_id: int, line_id: int
    ) -> AnnualReportIncomeLine | None:
        return self.db.scalars(
            select(AnnualReportIncomeLine).where(
                AnnualReportIncomeLine.id == line_id,
                AnnualReportIncomeLine.annual_report_id == annual_report_id,
            )
        ).first()

    def apply_updates(
        self, line: AnnualReportIncomeLine, fields: dict[str, Any]
    ) -> AnnualReportIncomeLine:
        for k, v in fields.items():
            if k not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Unsupported income line update field: {k}")
            setattr(line, k, v)
        self.db.flush()
        return line

    def delete_line(self, line: AnnualReportIncomeLine) -> None:
        self.db.delete(line)
        self.db.flush()

    def total_income(self, annual_report_id: int) -> Decimal:
        result = self.db.scalar(
            select(func.coalesce(func.sum(AnnualReportIncomeLine.amount), 0)).where(
                AnnualReportIncomeLine.annual_report_id == annual_report_id
            )
        )
        return Decimal(str(result))


__all__ = ["AnnualReportIncomeRepository"]
