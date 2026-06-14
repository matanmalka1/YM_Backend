"""Read-only queries for VatWorkItem entities."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.common.enums import VatType
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_filters import (
    apply_vat_work_item_filters,
)

_FILED_STATUSES = {
    VatWorkItemStatus.FILED,
    VatWorkItemStatus.CANCELED,
}


class VatWorkItemQueryRepository(BaseRepository[VatWorkItem]):
    model = VatWorkItem

    def __init__(self, db: Session):
        super().__init__(db)

    def _query(self, status: VatWorkItemStatus | None = None):
        stmt = scope_to_active_clients_stmt(
            select(VatWorkItem),
            VatWorkItem,
        ).where(VatWorkItem.deleted_at.is_(None))
        return stmt.where(VatWorkItem.status == status) if status is not None else stmt

    def _filtered_query(
        self,
        status: VatWorkItemStatus | None = None,
        period: str | None = None,
        client_record_ids: list[int] | None = None,
        period_type: VatType | None = None,
        client_name: str | None = None,
    ):
        stmt = apply_vat_work_item_filters(
            self._query(status),
            period=period,
            client_record_ids=client_record_ids,
            period_type=period_type,
        )
        if client_name:
            term = f"%{client_name.strip()}%"
            stmt = stmt.join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id).where(
                LegalEntity.official_name.ilike(term)
                | func.coalesce(LegalEntity.id_number, "").ilike(term)
            )
        return stmt

    def get_by_client_record_period(self, client_record_id: int, period: str) -> VatWorkItem | None:
        return self.db.scalars(
            select(VatWorkItem).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.period == period,
                VatWorkItem.deleted_at.is_(None),
            )
        ).first()

    def list_by_client_record(self, client_record_id: int, limit: int = 200) -> list[VatWorkItem]:
        return self.db.scalars(
            select(VatWorkItem)
            .where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.deleted_at.is_(None),
            )
            .order_by(VatWorkItem.period.desc())
            .limit(limit)
        ).all()

    @staticmethod
    def _client_work_item_filters(
        client_record_id: int,
        *,
        year: int | None = None,
        period: str | None = None,
        status: VatWorkItemStatus | None = None,
        assigned_to: int | None = None,
        due_after: date | None = None,
        due_before: date | None = None,
    ) -> list:
        """Filter set shared by the client work-item list and count queries.

        ``client_record_id`` path scope and the not-deleted constraint always
        apply; optional operational filters narrow the result further (they never
        widen access).
        """
        filters = [
            VatWorkItem.client_record_id == client_record_id,
            VatWorkItem.deleted_at.is_(None),
        ]
        if year is not None:
            filters.append(VatWorkItem.period.startswith(f"{year}-"))
        if period:
            filters.append(VatWorkItem.period == period)
        if status is not None:
            filters.append(VatWorkItem.status == status)
        if assigned_to is not None:
            filters.append(VatWorkItem.assigned_to == assigned_to)
        if due_after is not None:
            filters.append(VatWorkItem.due_date_effective >= due_after)
        if due_before is not None:
            filters.append(VatWorkItem.due_date_effective <= due_before)
        return filters

    def list_by_client_record_paginated(
        self,
        client_record_id: int,
        page: int = 1,
        page_size: int = 200,
        *,
        year: int | None = None,
        period: str | None = None,
        status: VatWorkItemStatus | None = None,
        assigned_to: int | None = None,
        due_after: date | None = None,
        due_before: date | None = None,
    ) -> list[VatWorkItem]:
        filters = self._client_work_item_filters(
            client_record_id,
            year=year,
            period=period,
            status=status,
            assigned_to=assigned_to,
            due_after=due_after,
            due_before=due_before,
        )
        stmt = (
            select(VatWorkItem)
            .where(*filters)
            .order_by(VatWorkItem.period.desc(), VatWorkItem.id.desc())
        )
        return list(self.db.scalars(self.apply_pagination(stmt, page, page_size)).all())

    def count_by_client_record(
        self,
        client_record_id: int,
        *,
        year: int | None = None,
        period: str | None = None,
        status: VatWorkItemStatus | None = None,
        assigned_to: int | None = None,
        due_after: date | None = None,
        due_before: date | None = None,
    ) -> int:
        filters = self._client_work_item_filters(
            client_record_id,
            year=year,
            period=period,
            status=status,
            assigned_to=assigned_to,
            due_after=due_after,
            due_before=due_before,
        )
        return self.db.scalar(select(func.count(VatWorkItem.id)).where(*filters))

    def list_by_business_activity(
        self, business_activity_id: int, limit: int = 200
    ) -> list[VatWorkItem]:
        from app.vat.models.vat_invoice import VatInvoice

        return self.db.scalars(
            select(VatWorkItem)
            .join(VatInvoice, VatInvoice.work_item_id == VatWorkItem.id)
            .where(
                VatInvoice.business_activity_id == business_activity_id,
                VatWorkItem.deleted_at.is_(None),
            )
            .distinct()
            .order_by(VatWorkItem.period.desc())
            .limit(limit)
        ).all()

    def list_by_status(
        self,
        status: VatWorkItemStatus,
        page: int = 1,
        page_size: int = 20,
        period: str | None = None,
        client_record_ids: list[int] | None = None,
        period_type: VatType | None = None,
        client_name: str | None = None,
    ) -> list[VatWorkItem]:
        stmt = self._filtered_query(status, period, client_record_ids, period_type, client_name)
        stmt = self.apply_pagination(stmt.order_by(VatWorkItem.period.desc()), page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_by_status(
        self,
        status: VatWorkItemStatus,
        period: str | None = None,
        client_record_ids: list[int] | None = None,
        period_type: VatType | None = None,
        client_name: str | None = None,
    ) -> int:
        stmt = self._filtered_query(status, period, client_record_ids, period_type, client_name)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return self.db.scalar(count_stmt)

    def count_by_status_summary(
        self,
        *,
        year: int | None = None,
        period_type: VatType | None = None,
        client_record_id: int | None = None,
        client_name: str | None = None,
    ) -> dict[VatWorkItemStatus, int]:
        stmt = scope_to_active_clients_stmt(
            select(VatWorkItem.status, func.count(VatWorkItem.id)),
            VatWorkItem,
        ).where(VatWorkItem.deleted_at.is_(None))
        if year is not None:
            stmt = stmt.where(VatWorkItem.period.startswith(f"{year}-"))
        if period_type is not None:
            stmt = stmt.where(VatWorkItem.period_type == period_type)
        if client_record_id is not None:
            stmt = stmt.where(VatWorkItem.client_record_id == client_record_id)
        if client_name:
            term = f"%{client_name.strip()}%"
            stmt = stmt.join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id).where(
                LegalEntity.official_name.ilike(term)
                | func.coalesce(LegalEntity.id_number, "").ilike(term)
            )
        rows = self.db.execute(stmt.group_by(VatWorkItem.status)).all()
        return {status: int(count) for status, count in rows}

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        period: str | None = None,
        client_record_ids: list[int] | None = None,
        period_type: VatType | None = None,
        client_name: str | None = None,
    ) -> list[VatWorkItem]:
        stmt = self._filtered_query(None, period, client_record_ids, period_type, client_name)
        stmt = self.apply_pagination(stmt.order_by(VatWorkItem.period.desc()), page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_all(
        self,
        period: str | None = None,
        client_record_ids: list[int] | None = None,
        period_type: VatType | None = None,
        client_name: str | None = None,
    ) -> int:
        stmt = self._filtered_query(None, period, client_record_ids, period_type, client_name)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return self.db.scalar(count_stmt)

    def count_by_period_not_filed(self, period: str) -> int:
        return self.db.scalar(
            select(func.count(VatWorkItem.id))
            .join(ClientRecord, ClientRecord.id == VatWorkItem.client_record_id)
            .where(
                VatWorkItem.period == period,
                VatWorkItem.status != VatWorkItemStatus.FILED,
                VatWorkItem.deleted_at.is_(None),
                ClientRecord.deleted_at.is_(None),
            )
        )

    def sum_net_vat_by_client_record_year(
        self, client_record_id: int, tax_year: int
    ) -> float | None:
        row = self.db.execute(
            select(func.sum(VatWorkItem.net_vat).label("total_vat")).where(
                VatWorkItem.client_record_id == client_record_id,
                func.substr(VatWorkItem.period, 1, 4) == str(tax_year),
                VatWorkItem.deleted_at.is_(None),
            )
        ).one_or_none()
        return float(row[0]) if row and row[0] is not None else None

    def list_not_filed_for_period(self, period: str, limit: int = 3) -> list[VatWorkItem]:
        return self.db.scalars(
            scope_to_active_clients_stmt(select(VatWorkItem), VatWorkItem)
            .where(
                VatWorkItem.period == period,
                VatWorkItem.status != VatWorkItemStatus.FILED,
                VatWorkItem.deleted_at.is_(None),
            )
            .order_by(VatWorkItem.created_at.asc())
            .limit(limit)
        ).all()

    def list_open_up_to_period(self, up_to_period: str, limit: int = 50) -> list[VatWorkItem]:
        return self.db.scalars(
            scope_to_active_clients_stmt(select(VatWorkItem), VatWorkItem)
            .where(
                VatWorkItem.period <= up_to_period,
                VatWorkItem.status.notin_(list(_FILED_STATUSES)),
                VatWorkItem.deleted_at.is_(None),
            )
            .order_by(VatWorkItem.period.asc())
            .limit(limit)
        ).all()
