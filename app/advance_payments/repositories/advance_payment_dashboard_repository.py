from sqlalchemy import case, func, select, tuple_
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.common.repositories.base_repository import BaseRepository


class AdvancePaymentDashboardRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def completion_for_period(self, period: str, period_months_count: int) -> tuple[int, int]:
        paid_expr = case(
            (AdvancePayment.status == AdvancePaymentStatus.PAID, 1),
            else_=0,
        )
        stmt = scope_to_active_clients_stmt(
            select(
                func.coalesce(func.sum(paid_expr), 0),
                func.count(AdvancePayment.id),
            ),
            AdvancePayment,
        ).where(
            AdvancePayment.period == period,
            AdvancePayment.period_months_count == period_months_count,
            AdvancePayment.deleted_at.is_(None),
        )
        completed, total = self.db.execute(stmt).one()
        return int(completed or 0), int(total or 0)

    def completion_for_periods(
        self, periods: list[tuple[str, int]]
    ) -> dict[tuple[str, int], tuple[int, int]]:
        if not periods:
            return {}
        paid_expr = case(
            (AdvancePayment.status == AdvancePaymentStatus.PAID, 1),
            else_=0,
        )
        stmt = scope_to_active_clients_stmt(
            select(
                AdvancePayment.period,
                AdvancePayment.period_months_count,
                func.coalesce(func.sum(paid_expr), 0),
                func.count(AdvancePayment.id),
            ),
            AdvancePayment,
        ).where(
            AdvancePayment.deleted_at.is_(None),
            tuple_(AdvancePayment.period, AdvancePayment.period_months_count).in_(periods),
        )
        stmt = stmt.group_by(AdvancePayment.period, AdvancePayment.period_months_count)
        result = {period: (0, 0) for period in periods}
        for period, months_count, completed, total in self.db.execute(stmt).all():
            result[(period, int(months_count))] = (int(completed or 0), int(total or 0))
        return result
