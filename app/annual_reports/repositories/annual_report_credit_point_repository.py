from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_credit_point_reason import (
    AnnualReportCreditPoint,
    CreditPointReason,
)
from app.common.repositories.base_repository import BaseRepository

_ZERO = Decimal("0")
_TUITION_REASONS = frozenset(
    {
        CreditPointReason.ACADEMIC_DEGREE,
    }
)


class AnnualReportCreditPointRepository(BaseRepository[AnnualReportCreditPoint]):
    def __init__(self, db: Session):
        self.db = db

    def list_by_report_id(self, report_id: int) -> list[AnnualReportCreditPoint]:
        return self.db.scalars(
            select(AnnualReportCreditPoint)
            .where(AnnualReportCreditPoint.annual_report_id == report_id)
            .order_by(AnnualReportCreditPoint.id.asc())
        ).all()

    def create(
        self,
        annual_report_id: int,
        reason: CreditPointReason,
        points: Decimal,
        notes: str | None = None,
    ) -> AnnualReportCreditPoint:
        row = AnnualReportCreditPoint(
            annual_report_id=annual_report_id,
            reason=reason,
            points=points,
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def aggregate_breakdown(
        self, report_id: int, default_resident_points: Decimal
    ) -> dict[str, Decimal]:
        rows = self.list_by_report_id(report_id)
        if not rows:
            return {
                "credit_points": default_resident_points,
                "pension_credit_points": _ZERO,
                "life_insurance_credit_points": _ZERO,
                "tuition_credit_points": _ZERO,
                "total_credit_points": default_resident_points,
            }

        base = _ZERO
        tuition = _ZERO
        pension = _ZERO
        life_insurance = _ZERO
        total = _ZERO

        for row in rows:
            total += Decimal(str(row.points))
            if row.reason in _TUITION_REASONS:
                tuition += Decimal(str(row.points))
            else:
                base += Decimal(str(row.points))

        return {
            "credit_points": base,
            "pension_credit_points": pension,
            "life_insurance_credit_points": life_insurance,
            "tuition_credit_points": tuition,
            "total_credit_points": total,
        }

    def total_points_by_report_id(
        self, report_id: int, default_resident_points: Decimal
    ) -> Decimal:
        total = self.db.scalar(
            select(func.coalesce(func.sum(AnnualReportCreditPoint.points), 0)).where(
                AnnualReportCreditPoint.annual_report_id == report_id
            )
        )
        if total in (None, 0):
            return default_resident_points
        return Decimal(str(total))


__all__ = ["AnnualReportCreditPointRepository"]
