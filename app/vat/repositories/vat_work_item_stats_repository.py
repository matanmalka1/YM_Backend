from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.common.enums import ObligationStatus, VatType
from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_work_item import VatWorkItem


class VatWorkItemStatsRepository(BaseRepository[VatWorkItem]):
    def __init__(self, db: Session):
        self.db = db

    def count_closed_by_period_type(self, period: str, vat_type: VatType) -> int:
        return self.db.scalar(
            select(func.count(VatWorkItem.id)).where(
                VatWorkItem.period == period,
                VatWorkItem.period_type == vat_type,
                VatWorkItem.status == ObligationStatus.SUBMITTED,
                VatWorkItem.deleted_at.is_(None),
            )
        )

    def count_closed_by_period_types(
        self, period_types: list[tuple[str, VatType]]
    ) -> dict[tuple[str, VatType], int]:
        if not period_types:
            return {}
        stmt = (
            select(VatWorkItem.period, VatWorkItem.period_type, func.count(VatWorkItem.id))
            .where(
                VatWorkItem.status == ObligationStatus.SUBMITTED,
                VatWorkItem.deleted_at.is_(None),
                tuple_(VatWorkItem.period, VatWorkItem.period_type).in_(period_types),
            )
            .group_by(VatWorkItem.period, VatWorkItem.period_type)
        )
        counts = {period_type: 0 for period_type in period_types}
        for period, vat_type, count in self.db.execute(stmt).all():
            counts[(period, vat_type)] = int(count)
        return counts
