"""CRUD repository for AdvancePayment entities."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app.advance_payments.models.advance_payment import AdvancePayment
from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    advance_payment_year_range_filter,
)
from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.common.enums import ObligationStatus
from app.common.obligation_chain import (
    link_amendment,
    select_current_obligation,
    select_obligations,
    select_slot_occupant,
)
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
        assigned_to: int | None = None,
        expected_amount=None,
        paid_amount: Decimal | None = None,
        payment_method=None,
        payment_reference: str | None = None,
        annual_report_id: int | None = None,
        tax_calendar_entry_id: int | None = None,
        notes: str | None = None,
        advance_rate=None,
        turnover_amount=None,
        turnover_source=None,
        turnover_snapshot_at=None,
        calculated_amount=None,
        override_amount=None,
        withheld_amount=None,
        status: ObligationStatus = ObligationStatus.AWAITING_INPUT,
    ) -> AdvancePayment:
        payment = AdvancePayment(
            client_record_id=client_record_id,
            assigned_to=assigned_to,
            period=period,
            period_months_count=period_months_count,
            due_date=due_date,
            expected_amount=expected_amount if expected_amount is not None else Decimal("0"),
            paid_amount=paid_amount if paid_amount is not None else Decimal("0"),
            payment_method=payment_method,
            payment_reference=payment_reference,
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
            withheld_amount=withheld_amount,
        )
        self.db.add(payment)
        self.db.flush()
        return payment

    def create_amendment(self, original: AdvancePayment, *, fields: dict) -> AdvancePayment:
        """Persist a correction of ``original``, linked to it.

        ``fields`` arrives already decided by the service — what an amendment
        inherits and what it must not (D-14, D-21) is a domain question. An
        advance has no child rows to carry: its figures are its own columns, so
        the copy is the row and the link, and nothing else.
        """
        amendment = AdvancePayment(**fields)
        link_amendment(amendment, original)
        self.db.add(amendment)
        self.db.flush()
        return amendment

    def get_by_id_for_client_record(
        self, payment_id: int, client_record_id: int
    ) -> AdvancePayment | None:
        """One payment, scoped to its client — identity, not a list.

        Superseded rows stay reachable. D-12 is a rule about lists, counts and
        sums; a record asked for *by id* is a record someone deliberately opened,
        and a corrected period whose original could not be opened would make the
        chain history unreadable — the thing amendments exist to preserve.
        """
        return self.db.scalars(
            select_obligations(AdvancePayment, include_superseded=True).where(
                AdvancePayment.id == payment_id,
                AdvancePayment.client_record_id == client_record_id,
            )
        ).first()

    def get_active_by_ids(self, payment_ids: list[int]) -> list[AdvancePayment]:
        """Active (non-deleted) payments by id, across clients — org-level bulk ops."""
        if not payment_ids:
            return []
        return list(
            self.db.scalars(
                select_obligations(AdvancePayment).where(
                    AdvancePayment.id.in_(payment_ids),
                )
            ).all()
        )

    def list_by_client_record_year(
        self,
        client_record_id: int,
        year: int,
        status: list[ObligationStatus] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AdvancePayment], int]:
        base_where = [
            AdvancePayment.client_record_id == client_record_id,
            advance_payment_year_range_filter(year),
        ]
        if status:
            base_where.append(AdvancePayment.status.in_(status))
        total = self.db.scalar(
            select_obligations(AdvancePayment, func.count(AdvancePayment.id)).where(*base_where)
        )
        stmt = (
            select_obligations(AdvancePayment)
            .where(*base_where)
            .order_by(AdvancePayment.period.asc())
        )
        stmt = self.apply_pagination(stmt, page, page_size)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def list_due_for_work_queue(
        self, cutoff: date, client_record_id: int | None = None
    ) -> list[AdvancePayment]:
        """Active-client periods that still need work: due by ``cutoff``, or undated.

        Uses ``due_date_effective`` when set, otherwise the snapshot ``due_date``.
        A row with neither is an amendment (D-14) — it is still live work someone
        must finish, and a deadline filter that dropped it would hide a real
        obligation from the one list whose purpose is to surface unfinished work.
        """
        stmt = scope_to_active_clients_stmt(
            select_obligations(AdvancePayment), AdvancePayment
        ).where(
            AdvancePayment.status.in_(
                [ObligationStatus.AWAITING_INPUT, ObligationStatus.IN_PROGRESS]
            ),
            (AdvancePayment.due_date_effective <= cutoff)
            | (AdvancePayment.due_date_effective.is_(None) & (AdvancePayment.due_date <= cutoff))
            | (AdvancePayment.due_date_effective.is_(None) & AdvancePayment.due_date.is_(None)),
        )
        if client_record_id is not None:
            stmt = stmt.where(AdvancePayment.client_record_id == client_record_id)
        return list(self.db.scalars(stmt).all())

    def list_from_period(self, client_record_id: int, from_period: str) -> list[AdvancePayment]:
        """Active (non-deleted) advance payments for a client at or after ``from_period``.

        Periods are ``YYYY-MM`` strings, so a lexical ``>=`` matches chronological
        order. Callers partition by status themselves (bulk rate update reprices
        only PENDING rows and reports the rest as skipped).
        """
        return list(
            self.db.scalars(
                select_obligations(AdvancePayment)
                .where(
                    AdvancePayment.client_record_id == client_record_id,
                    AdvancePayment.period >= from_period,
                )
                .order_by(AdvancePayment.period.asc())
            ).all()
        )

    def list_stale_cadence_for_year(
        self, client_record_id: int, year: int, period_months_count: int
    ) -> list[AdvancePayment]:
        """Payments in ``year`` left over from a different reporting cadence.

        A client whose frequency changed keeps rows whose ``period_months_count``
        no longer matches the configured one. ``get_slot_occupant_for_period``
        matches on the ``YYYY-MM`` key alone, so those rows block the new schedule
        instead of being replaced by it. Callers partition by status and due date
        themselves.
        """
        return list(
            self.db.scalars(
                select_obligations(AdvancePayment)
                .where(
                    AdvancePayment.client_record_id == client_record_id,
                    advance_payment_year_range_filter(year),
                    AdvancePayment.period_months_count != period_months_count,
                )
                .order_by(AdvancePayment.period.asc())
            ).all()
        )

    def get_slot_occupant_for_period(
        self, client_record_id: int, period: str
    ) -> AdvancePayment | None:
        """The payment holding this period's slot, for creation gates only."""
        return self.db.scalars(
            select_slot_occupant(
                AdvancePayment,
                client_record_id=client_record_id,
                period_column=AdvancePayment.period,
                period_value=period,
            )
        ).first()

    def get_by_period(self, client_record_id: int, period: str) -> AdvancePayment | None:
        """The period's operational payment — what it displays and what work acts on."""
        return self.db.scalars(
            select_current_obligation(
                AdvancePayment,
                client_record_id=client_record_id,
                period_column=AdvancePayment.period,
                period_value=period,
            )
        ).first()

    def update_payment(self, payment: AdvancePayment, **fields) -> AdvancePayment:
        return self._update_entity(payment, touch_updated_at=True, **fields)

    def soft_delete(self, payment_id: int, deleted_by: int | None = None) -> bool:
        return self._soft_delete_entity(payment_id, deleted_by)
