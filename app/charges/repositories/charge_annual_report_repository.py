"""Charge queries scoped to a specific annual report."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.charges.models.charge import Charge
from app.common.repositories.base_repository import BaseRepository


class ChargeAnnualReportRepository(BaseRepository):
    """Charge queries used by the annual_reports domain."""

    def __init__(self, db: Session):
        super().__init__(db)

    def list_by_annual_report(
        self,
        annual_report_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Charge], int]:
        """Return paginated charges linked to an annual report and their total count."""
        where = (
            Charge.annual_report_id == annual_report_id,
            Charge.deleted_at.is_(None),
        )
        total = self.db.scalar(select(func.count(Charge.id)).where(*where))
        stmt = select(Charge).where(*where).order_by(Charge.created_at.desc())
        stmt = self.apply_pagination(stmt, page, page_size)
        items = list(self.db.scalars(stmt).all())
        return items, total
