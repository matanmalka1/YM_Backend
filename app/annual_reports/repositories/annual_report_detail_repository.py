from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_detail import AnnualReportDetail
from app.common.repositories.base_repository import BaseRepository

_META_COLUMNS = frozenset(
    {
        "client_approved_at",
        "internal_notes",
        "amendment_reason",
        "pension_contribution",
        "donation_amount",
        "other_credits",
    }
)


class AnnualReportDetailRepository(BaseRepository[AnnualReportDetail]):
    def __init__(self, db: Session):
        self.db = db

    def get_by_report_id(self, report_id: int) -> AnnualReportDetail | None:
        return self.db.scalars(
            select(AnnualReportDetail).where(AnnualReportDetail.report_id == report_id)
        ).first()

    def update_meta(self, report_id: int, **fields) -> AnnualReportDetail:
        """Update only business metadata columns (approval, notes, amendment reason, deductions)."""
        return self._upsert(report_id, fields, allowed=_META_COLUMNS)

    def _upsert(self, report_id: int, fields: dict, allowed: frozenset) -> AnnualReportDetail:
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(
                f"AnnualReportDetailRepository: unexpected columns {unknown}. "
                f"Use the correct method for cache vs metadata writes."
            )
        detail = self.get_by_report_id(report_id)
        if detail is None:
            detail = AnnualReportDetail(report_id=report_id, **fields)
            self.db.add(detail)
        else:
            for key, value in fields.items():
                setattr(detail, key, value)
        self.db.flush()
        return detail


__all__ = ["AnnualReportDetailRepository"]
