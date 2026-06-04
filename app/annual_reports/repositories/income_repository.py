"""Repository for AnnualReportIncomeLine entities."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_income_line import (
    AnnualReportIncomeLine,
    IncomeSourceType,
)
from app.common.repositories.base_repository import BaseRepository


class AnnualReportIncomeRepository(BaseRepository[AnnualReportIncomeLine]):
    _UPDATABLE_FIELDS = {"source_type", "amount", "description"}

    def __init__(self, db: Session):
        self.db = db

    def add_line(
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

    def get_by_id(self, line_id: int) -> AnnualReportIncomeLine | None:
        raise NotImplementedError(
            "AnnualReportIncomeRepository.get_by_id is unsafe for annual report financial lines; "
            "use get_by_report_and_id(report_id, line_id)."
        )

    def get_by_report_and_id(
        self, annual_report_id: int, line_id: int
    ) -> AnnualReportIncomeLine | None:
        return self.db.scalars(
            select(AnnualReportIncomeLine).where(
                AnnualReportIncomeLine.id == line_id,
                AnnualReportIncomeLine.annual_report_id == annual_report_id,
            )
        ).first()

    def update(self, line_id: int, **fields) -> AnnualReportIncomeLine | None:
        raise NotImplementedError(
            "AnnualReportIncomeRepository.update is unsafe; "
            "use update_for_report(report_id, line_id, **fields)."
        )

    def update_for_report(
        self, annual_report_id: int, line_id: int, **fields
    ) -> AnnualReportIncomeLine | None:
        line = self.get_by_report_and_id(annual_report_id, line_id)
        if not line:
            return None
        for k, v in fields.items():
            if k not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Unsupported income line update field: {k}")
            setattr(line, k, v)
        self.db.flush()
        return line

    def delete(
        self,
        line_id: int,
        deleted_by: int | None = None,  # pylint: disable=unused-argument
        *,
        hard: bool = False,  # pylint: disable=unused-argument
    ) -> bool:
        raise NotImplementedError(
            "AnnualReportIncomeRepository.delete is unsafe; "
            "use delete_for_report(report_id, line_id)."
        )

    def delete_for_report(self, annual_report_id: int, line_id: int) -> bool:
        line = self.get_by_report_and_id(annual_report_id, line_id)
        if not line:
            return False
        self.db.delete(line)
        self.db.flush()
        return True

    def total_income(self, annual_report_id: int) -> Decimal:
        result = self.db.scalar(
            select(func.coalesce(func.sum(AnnualReportIncomeLine.amount), 0)).where(
                AnnualReportIncomeLine.annual_report_id == annual_report_id
            )
        )
        return Decimal(str(result))


__all__ = ["AnnualReportIncomeRepository"]
