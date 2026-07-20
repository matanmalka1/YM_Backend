"""CRUD repository for AdvancePayment entities."""

from datetime import date
from decimal import Decimal

from sqlalchemy import exists, func, select

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    advance_payment_year_range_filter,
)
from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.common.repositories.base_repository import BaseRepository


class AdvancePaymentRepository(BaseRepository[AdvancePayment]):
    model = AdvancePayment

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int,
        due_date: date,
        expected_amount=None,
        paid_amount: Decimal | None = None,
        payment_method=None,
        annual_report_id: int | None = None,
        tax_calendar_entry_id: int | None = None,
        notes: str | None = None,
        advance_rate=None,
        turnover_amount=None,
        turnover_source=None,
        turnover_snapshot_at=None,
        calculated_amount=None,
        override_amount=None,
        status: AdvancePaymentStatus = AdvancePaymentStatus.PENDING,
    ) -> AdvancePayment:
        payment = AdvancePayment(
            client_record_id=client_record_id,
            period=period,
            period_months_count=period_months_count,
            due_date=due_date,
            expected_amount=expected_amount if expected_amount is not None else Decimal("0"),
            paid_amount=paid_amount if paid_amount is not None else Decimal("0"),
            payment_method=payment_method,
            annual_report_id=annual_report_id,
            tax_calendar_entry_id=tax_calendar_entry_id,
            notes=notes,
            status=status,
            advance_rate=advance_rate,
            turnover_amount=turnover_amount,
            turnover_source=turnover_source,
            turnover_snapshot_at=turnover_snapshot_at,
            calculated_amount=calculated_amount if calculated_amount is not None else Decimal("0"),
            override_amount=override_amount,
        )
        self.db.add(payment)
        self.db.flush()
        return payment

    def get_by_id_for_client_record(
        self, payment_id: int, client_record_id: int
    ) -> AdvancePayment | None:
        return self.db.scalars(
            select(AdvancePayment).where(
                AdvancePayment.id == payment_id,
                AdvancePayment.client_record_id == client_record_id,
                AdvancePayment.deleted_at.is_(None),
            )
        ).first()

    def list_by_client_record_year(
        self,
        client_record_id: int,
        year: int,
        status: list[AdvancePaymentStatus] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AdvancePayment], int]:
        base_where = [
            AdvancePayment.client_record_id == client_record_id,
            advance_payment_year_range_filter(year),
            AdvancePayment.deleted_at.is_(None),
        ]
        if status:
            base_where.append(AdvancePayment.status.in_(status))
        total = self.db.scalar(select(func.count(AdvancePayment.id)).where(*base_where))
        stmt = select(AdvancePayment).where(*base_where).order_by(AdvancePayment.period.asc())
        stmt = self.apply_pagination(stmt, page, page_size)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def list_due_for_work_queue(
        self, cutoff: date, client_record_id: int | None = None
    ) -> list[AdvancePayment]:
        """Active-client pending/partial advance payments due on or before ``cutoff``.

        Uses ``due_date_effective`` when set, otherwise the snapshot ``due_date``.
        """
        stmt = scope_to_active_clients_stmt(select(AdvancePayment), AdvancePayment).where(
            AdvancePayment.deleted_at.is_(None),
            AdvancePayment.status.in_([AdvancePaymentStatus.PENDING, AdvancePaymentStatus.PARTIAL]),
            (AdvancePayment.due_date_effective <= cutoff)
            | (AdvancePayment.due_date_effective.is_(None) & (AdvancePayment.due_date <= cutoff)),
        )
        if client_record_id is not None:
            stmt = stmt.where(AdvancePayment.client_record_id == client_record_id)
        return list(self.db.scalars(stmt).all())

    def exists_for_period(self, client_record_id: int, period: str) -> bool:
        return self.db.scalar(
            select(
                exists(
                    select(AdvancePayment.id).where(
                        AdvancePayment.client_record_id == client_record_id,
                        AdvancePayment.period == period,
                        AdvancePayment.deleted_at.is_(None),
                    )
                )
            )
        )

    def get_by_period(self, client_record_id: int, period: str) -> AdvancePayment | None:
        return self.db.scalars(
            select(AdvancePayment).where(
                AdvancePayment.client_record_id == client_record_id,
                AdvancePayment.period == period,
                AdvancePayment.deleted_at.is_(None),
            )
        ).first()

    def update_payment(self, payment: AdvancePayment, **fields) -> AdvancePayment:
        return self._update_entity(payment, touch_updated_at=True, **fields)

    def soft_delete(self, payment_id: int, deleted_by: int | None = None) -> bool:
        return self._soft_delete_entity(payment_id, deleted_by)
