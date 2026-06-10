from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.charges.models.charge import Charge, ChargeStatus
from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.common.repositories.base_repository import BaseRepository


class ChargeRepository(BaseRepository[Charge]):
    """Data access layer for Charge entities."""

    model = Charge

    def __init__(self, db: Session):
        super().__init__(db)

    def create(
        self,
        client_record_id: int,
        amount: float,
        charge_type: str,
        business_id: int | None = None,
        period: str | None = None,
        months_covered: int = 1,
        created_by: int | None = None,
    ) -> Charge:
        """Create new charge in draft status."""
        charge = Charge(
            client_record_id=client_record_id,
            business_id=business_id,
            amount=amount,
            charge_type=charge_type,
            period=period,
            months_covered=months_covered,
            status=ChargeStatus.DRAFT,
            created_by=created_by,
        )
        self.db.add(charge)
        self.db.flush()
        return charge

    def _base_stmt(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
        business_ids: list[int] | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
    ) -> object | None:
        """
        Shared filter builder for list and count queries.

        Filter priority:
        - client_record_id → always applied when provided (primary anchor)
        - business_id → narrows to a single business within the client
        - business_ids → narrows to a set of businesses (used by bulk/overview queries)
          Note: business_id and business_ids are mutually exclusive; business_id wins.

        Returns None when an explicit empty business_ids list is passed (caller wants
        zero results).
        """
        stmt = scope_to_active_clients_stmt(select(Charge), Charge).where(
            Charge.deleted_at.is_(None)
        )

        if client_record_id is not None:
            stmt = stmt.where(Charge.client_record_id == client_record_id)

        if business_id is not None:
            stmt = stmt.where(Charge.business_id == business_id)
        elif business_ids is not None:
            if not business_ids:
                # Explicit empty list → caller wants zero results
                return None
            stmt = stmt.where(Charge.business_id.in_(business_ids))

        if status:
            stmt = stmt.where(Charge.status == status)
        if charge_type:
            stmt = stmt.where(Charge.charge_type == charge_type)
        if period:
            stmt = stmt.where(Charge.period == period)
        if issued_after is not None:
            stmt = stmt.where(Charge.issued_at >= issued_after)
        if issued_before is not None:
            stmt = stmt.where(Charge.issued_at <= issued_before)

        return stmt

    def list_charges(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
        business_ids: list[int] | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Charge]:
        stmt = self._base_stmt(
            client_record_id,
            business_id,
            business_ids,
            status,
            charge_type,
            period,
            issued_after,
            issued_before,
        )
        if stmt is None:
            return []
        stmt = stmt.order_by(Charge.created_at.desc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def list_charges_by_client_record(
        self,
        client_record_id: int,
        business_id: int | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Charge]:
        return self.list_charges(
            client_record_id=client_record_id,
            business_id=business_id,
            status=status,
            charge_type=charge_type,
            period=period,
            issued_after=issued_after,
            issued_before=issued_before,
            page=page,
            page_size=page_size,
        )

    def count_charges(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
        business_ids: list[int] | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
    ) -> int:
        base = self._base_stmt(
            client_record_id,
            business_id,
            business_ids,
            status,
            charge_type,
            period,
            issued_after,
            issued_before,
        )
        if base is None:
            return 0
        count_stmt = base.with_only_columns(func.count(Charge.id))
        return self.db.scalar(count_stmt)

    def count_charges_by_client_record(
        self,
        client_record_id: int,
        business_id: int | None = None,
        status: str | None = None,
        charge_type: str | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
    ) -> int:
        return self.count_charges(
            client_record_id=client_record_id,
            business_id=business_id,
            status=status,
            charge_type=charge_type,
            period=period,
            issued_after=issued_after,
            issued_before=issued_before,
        )

    def sum_open_charges_amount(self) -> Decimal | None:
        """Sum all issued (open) charges for active clients. Returns None if no open charges."""
        stmt = scope_to_active_clients_stmt(select(func.sum(Charge.amount)), Charge).where(
            Charge.deleted_at.is_(None),
            Charge.status == ChargeStatus.ISSUED.value,
        )
        result = self.db.scalar(stmt)
        return Decimal(str(result)) if result is not None else None

    def open_charges_stats(self) -> tuple[int, Decimal | None]:
        stmt = scope_to_active_clients_stmt(
            select(
                func.count(Charge.id),
                func.sum(Charge.amount),
            ),
            Charge,
        ).where(
            Charge.deleted_at.is_(None),
            Charge.status == ChargeStatus.ISSUED.value,
        )
        count, total = self.db.execute(stmt).one()
        return int(count or 0), Decimal(str(total)) if total is not None else None

    def update_status(
        self,
        charge_id: int,
        new_status: ChargeStatus,
        charge: Charge | None = None,
        **additional_fields,
    ) -> Charge | None:
        """Update charge status and additional fields.

        Pass a pre-fetched (optionally locked) ``charge`` entity to avoid a second
        SELECT and to keep the lock acquired by get_by_id_for_update() in scope.
        """
        entity = charge or self.get_by_id(charge_id)
        return self._update_status(entity, new_status, **additional_fields)

    def stats_by_status(
        self,
        client_record_id: int | None = None,
        charge_type: str | None = None,
        business_id: int | None = None,
        period: str | None = None,
        issued_after: date | None = None,
        issued_before: date | None = None,
    ) -> dict[str, dict]:
        """Return count and total amount per status for the same filter slice as the list."""
        stmt = scope_to_active_clients_stmt(
            select(
                Charge.status,
                func.count(Charge.id).label("cnt"),
                func.sum(Charge.amount).label("total"),
            ),
            Charge,
        ).where(Charge.deleted_at.is_(None))
        if client_record_id is not None:
            stmt = stmt.where(Charge.client_record_id == client_record_id)
        if charge_type:
            stmt = stmt.where(Charge.charge_type == charge_type)
        if business_id is not None:
            stmt = stmt.where(Charge.business_id == business_id)
        if period is not None:
            stmt = stmt.where(Charge.period == period)
        if issued_after is not None:
            stmt = stmt.where(Charge.issued_at >= issued_after)
        if issued_before is not None:
            stmt = stmt.where(Charge.issued_at <= issued_before)
        stmt = stmt.group_by(Charge.status)
        rows = self.db.execute(stmt).all()
        return {
            str(s.value): {"count": cnt, "amount": str(total or Decimal(0))}
            for s, cnt, total in rows
        }

    def _aging_buckets_base_stmt(self, as_of_date: date):
        cut_30 = as_of_date - timedelta(days=30)
        cut_60 = as_of_date - timedelta(days=60)
        cut_90 = as_of_date - timedelta(days=90)
        issued_date = func.date(Charge.issued_at)
        return (
            scope_to_active_clients_stmt(
                select(
                    Charge.client_record_id,
                    func.sum(case((issued_date >= str(cut_30), Charge.amount), else_=0)).label(
                        "current"
                    ),
                    func.sum(
                        case(
                            (
                                issued_date.between(str(cut_60), str(cut_30 - timedelta(days=1))),
                                Charge.amount,
                            ),
                            else_=0,
                        )
                    ).label("days_30"),
                    func.sum(
                        case(
                            (
                                issued_date.between(str(cut_90), str(cut_60 - timedelta(days=1))),
                                Charge.amount,
                            ),
                            else_=0,
                        )
                    ).label("days_60"),
                    func.sum(case((issued_date < str(cut_90), Charge.amount), else_=0)).label(
                        "days_90_plus"
                    ),
                    func.sum(Charge.amount).label("total"),
                    func.min(Charge.issued_at).label("oldest_issued_at"),
                ),
                Charge,
            )
            .where(
                Charge.status == ChargeStatus.ISSUED.value,
                Charge.issued_at.isnot(None),
                Charge.deleted_at.is_(None),
            )
            .group_by(Charge.client_record_id)
        )

    def get_aging_buckets_paginated(
        self, as_of_date: date, *, page: int, page_size: int
    ) -> tuple[list, int]:
        """Paginated aging buckets ordered by total descending, with count of all groups."""
        base = self._aging_buckets_base_stmt(as_of_date).subquery()
        count = self.db.scalar(select(func.count()).select_from(base)) or 0
        rows = self.db.execute(
            select(base)
            .order_by(base.c.total.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
        return list(rows), count

    def get_aging_totals(self, as_of_date: date):
        """Sum across all client aging groups for the report summary row."""
        base = self._aging_buckets_base_stmt(as_of_date).subquery()
        return self.db.execute(
            select(
                func.coalesce(func.sum(base.c.current), 0).label("total_current"),
                func.coalesce(func.sum(base.c.days_30), 0).label("total_30_days"),
                func.coalesce(func.sum(base.c.days_60), 0).label("total_60_days"),
                func.coalesce(func.sum(base.c.days_90_plus), 0).label("total_90_plus"),
                func.coalesce(func.sum(base.c.total), 0).label("grand_total"),
                func.count(base.c.client_record_id).label("total_clients"),
            )
        ).one()

    def soft_delete(self, charge_id: int, deleted_by: int | None = None) -> bool:
        return self._soft_delete_entity(charge_id, deleted_by)
