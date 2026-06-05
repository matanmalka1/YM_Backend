from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    advance_payment_start_month_expr,
    advance_payment_year_range_filter,
)
from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.common.repositories.base_repository import BaseRepository


class AdvancePaymentBatchRepository(BaseRepository):
    def __init__(self, db: Session):
        super().__init__(db)

    def batch_summary_by_month(self, year: int | None) -> list:
        today_expr = func.current_date()
        start_month = advance_payment_start_month_expr()
        period_year = cast(func.substr(AdvancePayment.period, 1, 4), Integer)
        not_paid_expr = AdvancePayment.status != AdvancePaymentStatus.PAID
        pending_expr = AdvancePayment.status == AdvancePaymentStatus.PENDING
        effective_due_date = func.coalesce(
            AdvancePayment.due_date_effective, AdvancePayment.due_date
        )
        stmt = (
            scope_to_active_clients_stmt(
                select(
                    period_year.label("year"),
                    start_month.label("month"),
                    AdvancePayment.period_months_count,
                    func.max(AdvancePayment.due_date).label("due_date"),
                    func.count(AdvancePayment.id).label("client_count"),
                    func.coalesce(func.sum(AdvancePayment.expected_amount), 0).label(
                        "total_expected"
                    ),
                    func.coalesce(func.sum(AdvancePayment.paid_amount), 0).label("total_paid"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (effective_due_date < today_expr) & not_paid_expr,
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("overdue_count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    AdvancePayment.turnover_amount.is_(None),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("snapshot_missing_count"),
                    func.coalesce(
                        func.sum(case((pending_expr, 1), else_=0)),
                        0,
                    ).label("pending_count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    AdvancePayment.status == AdvancePaymentStatus.PAID,
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("paid_count"),
                ),
                AdvancePayment,
            )
            .where(
                *([advance_payment_year_range_filter(year)] if year is not None else []),
                AdvancePayment.deleted_at.is_(None),
            )
            .group_by(period_year, start_month, AdvancePayment.period_months_count)
            .order_by(period_year, start_month, AdvancePayment.period_months_count)
        )
        return self.db.execute(stmt).all()
