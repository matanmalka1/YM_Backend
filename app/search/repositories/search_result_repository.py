from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import EntityType
from app.common.repositories.base_repository import BaseRepository
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
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


@dataclass(frozen=True)
class PrimarySearchRow:
    result_type: Literal["client", "binder"]
    client_record_id: int
    office_client_number: int
    client_name: str
    id_number: str
    client_status: ClientStatus
    binder_id: int | None
    binder_number: str | None


class SearchResultRepository:
    """Cross-domain read projections for unified search."""

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

    def matching_client_ids(self, filters: SearchFilters) -> Select[tuple[int]]:
        """Return the advanced-filter client scope used by secondary result groups."""
        stmt = (
            select(ClientRecord.id)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.deleted_at.is_(None))
        )
        if filters.has_binder_filter:
            stmt = stmt.join(Binder, self._binder_join_conditions(filters))
            stmt = self._apply_binder_filters(stmt, filters)
        stmt = self._apply_client_filters(stmt, filters)
        return stmt.distinct()

    def search_primary(
        self, filters: SearchFilters, page: int, page_size: int
    ) -> tuple[list[PrimarySearchRow], int]:
        stmt = (
            select(
                ClientRecord.id.label("client_record_id"),
                ClientRecord.office_client_number,
                ClientRecord.status.label("client_status"),
                LegalEntity.official_name.label("client_name"),
                LegalEntity.id_number,
                Binder.id.label("binder_id"),
                Binder.binder_number,
            )
            .select_from(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .join(
                Binder,
                self._binder_join_conditions(filters),
                isouter=not filters.has_binder_filter,
            )
            .where(ClientRecord.deleted_at.is_(None))
        )
        stmt = self._apply_client_filters(stmt, filters)
        stmt = self._apply_binder_filters(stmt, filters)

        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            stmt = stmt.where(
                or_(
                    LegalEntity.official_name.ilike(pattern),
                    LegalEntity.id_number.ilike(pattern),
                    cast(ClientRecord.office_client_number, String).ilike(pattern),
                    Binder.binder_number.ilike(pattern),
                )
            )

        total = int(self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        stmt = stmt.order_by(
            LegalEntity.official_name.asc(),
            Binder.binder_number.asc().nulls_last(),
            ClientRecord.id,
        )
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        rows = self._db.execute(stmt).all()
        return (
            [
                PrimarySearchRow(
                    result_type="binder" if row.binder_id is not None else "client",
                    client_record_id=row.client_record_id,
                    office_client_number=row.office_client_number,
                    client_name=row.client_name,
                    id_number=row.id_number,
                    client_status=row.client_status,
                    binder_id=row.binder_id,
                    binder_number=row.binder_number,
                )
                for row in rows
            ],
            total,
        )

    def search_documents(
        self,
        *,
        query: str | None,
        filename: str | None,
        client_scope: Select[tuple[int]],
        limit: int,
    ) -> list[PermanentDocument]:
        stmt = select(PermanentDocument).where(
            PermanentDocument.client_record_id.in_(client_scope),
            PermanentDocument.is_deleted.is_(False),
            PermanentDocument.superseded_by.is_(None),
        )
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    PermanentDocument.original_filename.ilike(pattern),
                    cast(PermanentDocument.document_type, String).ilike(pattern),
                )
            )
        if filename:
            stmt = stmt.where(PermanentDocument.original_filename.ilike(f"%{filename.strip()}%"))
        return list(
            self._db.scalars(
                stmt.order_by(
                    PermanentDocument.uploaded_at.desc(), PermanentDocument.id.desc()
                ).limit(limit)
            ).all()
        )
