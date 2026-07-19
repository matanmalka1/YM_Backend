from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import EntityType
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity


@dataclass(frozen=True)
class SearchFilters:
    search: str | None = None
    client_record_id: int | None = None
    id_number: str | None = None
    client_status: ClientStatus | None = None
    entity_type: EntityType | None = None
    binder_number: str | None = None
    binder_location_status: BinderLocationStatus | None = None
    binder_capacity_status: BinderCapacityStatus | None = None

    @property
    def has_binder_filter(self) -> bool:
        return bool(
            self.binder_number or self.binder_location_status or self.binder_capacity_status
        )

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.search,
                self.client_record_id,
                self.id_number,
                self.client_status,
                self.entity_type,
                self.has_binder_filter,
            )
        )


@dataclass(frozen=True)
class ClientMatchRow:
    id: int
    office_client_number: int | None
    name: str
    id_number: str | None
    status: ClientStatus


class SearchResultRepository:
    """Resolves the typed term and advanced filters to the clients they identify."""

    def __init__(self, db: Session):
        self._db = db

    @staticmethod
    def _binder_join_conditions(filters: SearchFilters):
        conditions = [
            Binder.client_record_id == ClientRecord.id,
            Binder.deleted_at.is_(None),
        ]
        if filters.binder_location_status != BinderLocationStatus.HANDED_OVER:
            conditions.append(Binder.location_status != BinderLocationStatus.HANDED_OVER)
        return and_(*conditions)

    @staticmethod
    def _apply_client_filters(stmt, filters: SearchFilters):
        if filters.client_record_id is not None:
            stmt = stmt.where(ClientRecord.id == filters.client_record_id)
        if filters.id_number:
            stmt = stmt.where(LegalEntity.id_number.ilike(f"%{filters.id_number.strip()}%"))
        if filters.client_status is not None:
            stmt = stmt.where(ClientRecord.status == filters.client_status)
        if filters.entity_type is not None:
            stmt = stmt.where(LegalEntity.entity_type == filters.entity_type)
        return stmt

    @staticmethod
    def _apply_binder_filters(stmt, filters: SearchFilters):
        if filters.binder_number:
            stmt = stmt.where(Binder.binder_number.ilike(f"%{filters.binder_number.strip()}%"))
        if filters.binder_location_status is not None:
            stmt = stmt.where(Binder.location_status == filters.binder_location_status)
        if filters.binder_capacity_status is not None:
            stmt = stmt.where(Binder.capacity_status == filters.binder_capacity_status)
        return stmt

    @staticmethod
    def _term_match(term: str):
        """The term identifies a client by any of its public identifiers.

        A binder number counts as an identifier: it is how the office locates a client
        from physical material, so it resolves to the client that owns the binder.
        """
        pattern = f"%{term}%"
        return or_(
            LegalEntity.official_name.ilike(pattern),
            LegalEntity.id_number.ilike(pattern),
            cast(ClientRecord.office_client_number, String).ilike(pattern),
            exists(
                select(Binder.id).where(
                    Binder.client_record_id == ClientRecord.id,
                    Binder.deleted_at.is_(None),
                    Binder.location_status != BinderLocationStatus.HANDED_OVER,
                    Binder.binder_number.ilike(pattern),
                )
            ),
        )

    def search_clients(
        self, filters: SearchFilters, page: int, page_size: int
    ) -> tuple[list[ClientMatchRow], int]:
        """Clients matching the term and advanced filters, one row per client."""
        if filters.is_empty:
            return [], 0

        stmt = (
            select(
                ClientRecord.id,
                ClientRecord.office_client_number,
                LegalEntity.official_name.label("name"),
                LegalEntity.id_number,
                ClientRecord.status,
            )
            .select_from(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.deleted_at.is_(None))
        )
        if filters.has_binder_filter:
            stmt = stmt.join(Binder, self._binder_join_conditions(filters))
            stmt = self._apply_binder_filters(stmt, filters)
        stmt = self._apply_client_filters(stmt, filters)
        if filters.search:
            stmt = stmt.where(self._term_match(filters.search.strip()))
        stmt = stmt.distinct()

        total = int(self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        stmt = stmt.order_by(LegalEntity.official_name.asc(), ClientRecord.id)
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        return [
            ClientMatchRow(
                id=row.id,
                office_client_number=row.office_client_number,
                name=row.name,
                id_number=row.id_number,
                status=row.status,
            )
            for row in self._db.execute(stmt).all()
        ], total

    def matched_binder_numbers(
        self, client_ids: list[int], term: str | None
    ) -> dict[int, list[str]]:
        """Binder numbers that made each client match, so the choice is explainable.

        Empty when the term is not a binder number — there is nothing to explain then.
        """
        if not client_ids or not term:
            return {}
        rows = self._db.execute(
            select(Binder.client_record_id, Binder.binder_number)
            .where(
                Binder.client_record_id.in_(client_ids),
                Binder.deleted_at.is_(None),
                Binder.location_status != BinderLocationStatus.HANDED_OVER,
                Binder.binder_number.ilike(f"%{term.strip()}%"),
            )
            .order_by(Binder.binder_number)
        ).all()
        matches: dict[int, list[str]] = {}
        for client_record_id, binder_number in rows:
            matches.setdefault(client_record_id, []).append(binder_number)
        return matches
