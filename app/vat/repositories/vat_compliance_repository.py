"""Repository queries used exclusively by the VAT compliance report."""

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem


class VatComplianceRepository(BaseRepository[VatWorkItem]):
    def __init__(self, db: Session):
        self.db = db

    def _compliance_aggregates_base_stmt(self, year: int):
        year_str = str(year)
        filed_case = case((VatWorkItem.status == VatWorkItemStatus.FILED, 1), else_=0)
        return (
            scope_to_active_clients_stmt(
                select(
                    VatWorkItem.client_record_id,
                    VatWorkItem.period_type,
                    func.count(VatWorkItem.id).label("periods_expected"),
                    func.sum(filed_case).label("periods_filed"),
                ),
                VatWorkItem,
            )
            .where(
                func.substr(VatWorkItem.period, 1, 4) == year_str,
                VatWorkItem.deleted_at.is_(None),
            )
            .group_by(VatWorkItem.client_record_id, VatWorkItem.period_type)
            .order_by(VatWorkItem.client_record_id, VatWorkItem.period_type)
        )

    def get_compliance_aggregates_paginated(
        self, year: int, *, page: int, page_size: int
    ) -> tuple[list, int]:
        """Paginated compliance aggregates with total count of distinct client/period_type groups."""
        base = self._compliance_aggregates_base_stmt(year).subquery()
        count = self.db.scalar(select(func.count()).select_from(base)) or 0
        rows = (
            self.db.execute(
                select(base)
                .order_by(base.c.client_record_id, base.c.period_type)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .mappings()
            .all()
        )
        return list(rows), count

    def get_filed_items_for_clients(self, year: int, client_record_ids: list[int]) -> list:
        """Filed work items for a specific set of clients — used after page selection."""
        if not client_record_ids:
            return []
        year_str = str(year)
        stmt = scope_to_active_clients_stmt(
            select(
                VatWorkItem.client_record_id,
                VatWorkItem.period_type,
                VatWorkItem.period,
                VatWorkItem.filed_at,
                VatWorkItem.due_date_effective,
            ),
            VatWorkItem,
        ).where(
            func.substr(VatWorkItem.period, 1, 4) == year_str,
            VatWorkItem.status == VatWorkItemStatus.FILED,
            VatWorkItem.filed_at.isnot(None),
            VatWorkItem.deleted_at.is_(None),
            VatWorkItem.client_record_id.in_(client_record_ids),
        )
        return self.db.execute(stmt).all()

    def get_overdue_unfiled(self, reference_date: date) -> list[VatWorkItem]:
        """Work items whose period has passed and are not yet FILED.

        Returns full VatWorkItem rows so callers can read due_date_effective
        without issuing per-row queries.
        """
        stmt = (
            scope_to_active_clients_stmt(
                select(VatWorkItem),
                VatWorkItem,
            )
            .where(
                VatWorkItem.status.notin_(
                    [
                        VatWorkItemStatus.FILED,
                        VatWorkItemStatus.CANCELED,
                    ]
                ),
                VatWorkItem.deleted_at.is_(None),
                func.substr(VatWorkItem.period, 1, 7) < reference_date.strftime("%Y-%m"),
            )
            .order_by(VatWorkItem.period.asc())
        )
        return list(self.db.scalars(stmt))

    def get_stale_pending(self, year: int) -> list:
        """All PENDING_MATERIALS items for a year, ordered by updated_at."""
        year_str = str(year)
        stmt = (
            scope_to_active_clients_stmt(
                select(
                    VatWorkItem.client_record_id,
                    VatWorkItem.period,
                    VatWorkItem.updated_at,
                ),
                VatWorkItem,
            )
            .where(
                VatWorkItem.status == VatWorkItemStatus.PENDING_MATERIALS,
                func.substr(VatWorkItem.period, 1, 4) == year_str,
                VatWorkItem.deleted_at.is_(None),
            )
            .order_by(VatWorkItem.updated_at.asc())
        )
        return self.db.execute(stmt).all()
