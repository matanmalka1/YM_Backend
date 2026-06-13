from __future__ import annotations

from datetime import date

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.businesses.models.business import Business, BusinessStatus
from app.common.repositories.base_repository import BaseRepository
from app.utils.time_utils import utcnow


class BusinessRepository(BaseRepository[Business]):
    """Data access layer for Business entities."""

    model = Business

    def __init__(self, db: Session):
        super().__init__(db)

    # ─── Write ───────────────────────────────────────────────────────────────

    def create(
        self,
        legal_entity_id: int,
        opened_at: date,
        business_name: str | None = None,
        notes: str | None = None,
        created_by: int | None = None,
    ) -> Business:
        business = Business(
            legal_entity_id=legal_entity_id,
            business_name=business_name,
            opened_at=opened_at,
            notes=notes,
            created_by=created_by,
        )
        self.db.add(business)
        self.db.flush()
        return business

    def update(self, business_id: int, **fields) -> Business | None:
        business = self.get_by_id(business_id)
        return self._update_entity(business, **fields)

    def soft_delete(self, business_id: int, deleted_by: int | None = None) -> bool:
        business = self.get_by_id(business_id)
        if not business:
            return False
        business.deleted_at = utcnow()
        business.deleted_by = deleted_by
        self.db.flush()
        return True

    def restore(self, business_id: int, restored_by: int) -> Business | None:
        business = self.db.scalars(select(Business).where(Business.id == business_id)).first()
        if not business or business.deleted_at is None:
            return None
        business.deleted_at = None
        business.restored_at = utcnow()
        business.restored_by = restored_by
        business.status = BusinessStatus.ACTIVE
        self.db.flush()
        return business

    # ─── Read (single) ───────────────────────────────────────────────────────

    def get_by_id_including_deleted(self, business_id: int) -> Business | None:
        return self.db.scalars(select(Business).where(Business.id == business_id)).first()

    def exists_for_legal_entity(self, legal_entity_id: int) -> bool:
        return (
            self.db.scalars(
                select(Business).where(
                    Business.legal_entity_id == legal_entity_id,
                    Business.deleted_at.is_(None),
                )
            ).first()
        ) is not None

    def all_non_deleted_are_closed_for_legal_entity(self, legal_entity_id: int) -> bool:
        businesses = self.db.scalars(
            select(Business).where(
                Business.legal_entity_id == legal_entity_id,
                Business.deleted_at.is_(None),
            )
        ).all()
        return bool(businesses) and all(b.status == BusinessStatus.CLOSED for b in businesses)

    def get_ids_by_legal_entity(self, legal_entity_id: int) -> list[int]:
        rows = self.db.execute(
            select(Business.id).where(
                Business.legal_entity_id == legal_entity_id,
                Business.deleted_at.is_(None),
            )
        ).all()
        return [r[0] for r in rows]

    def has_conflicting_sole_trader(
        self,
        client_record_id: int,
        _new_type,
        _exclude_business_id: int | None = None,
    ) -> bool:
        return False

    # ─── Read (list) ─────────────────────────────────────────────────────────

    def _build_base_stmt(
        self,
        status: str | None = None,
        search: str | None = None,
    ):
        stmt = select(Business).where(Business.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Business.status == status)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                Business.business_name.ilike(term) | cast(Business.id, String).ilike(term)
            )
        return stmt

    def list(
        self,
        status: str | None = None,
        entity_type: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Business]:
        stmt = self._build_base_stmt(status, search).order_by(Business.opened_at.desc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return self.db.scalars(stmt).all()

    def count(
        self,
        status: str | None = None,
        entity_type: str | None = None,
        search: str | None = None,
        *,
        include_deleted: bool = False,
    ) -> int:
        base = self._build_base_stmt(status, search)
        return self.db.scalar(select(func.count()).select_from(base.subquery()))

    def list_by_legal_entity(
        self, legal_entity_id: int, page: int = 1, page_size: int = 20
    ) -> list[Business]:
        stmt = (
            select(Business)
            .where(
                Business.legal_entity_id == legal_entity_id,
                Business.deleted_at.is_(None),
            )
            .order_by(Business.opened_at.asc(), Business.id.asc())
        )
        stmt = self.apply_pagination(stmt, page, page_size)
        return self.db.scalars(stmt).all()

    def count_by_legal_entity(self, legal_entity_id: int) -> int:
        return self.db.scalar(
            select(func.count(Business.id)).where(
                Business.legal_entity_id == legal_entity_id,
                Business.deleted_at.is_(None),
            )
        )

    def list_by_legal_entity_including_deleted(self, legal_entity_id: int) -> list[Business]:
        return self.db.scalars(
            select(Business)
            .where(Business.legal_entity_id == legal_entity_id)
            .order_by(Business.deleted_at.asc().nullsfirst(), Business.opened_at.asc())
        ).all()

    def list_by_legal_entity_ids(self, legal_entity_ids: list[int]) -> list[Business]:
        if not legal_entity_ids:
            return []
        return self.db.scalars(
            select(Business).where(
                Business.legal_entity_id.in_(legal_entity_ids),
                Business.deleted_at.is_(None),
            )
        ).all()

    def list_by_ids(self, business_ids: list[int]) -> list[Business]:
        if not business_ids:
            return []
        return self.db.scalars(
            select(Business).where(Business.id.in_(business_ids), Business.deleted_at.is_(None))
        ).all()

    def list_all(self, status: str | None = None) -> list[Business]:
        """List all active businesses. No pagination — internal aggregation use only."""
        stmt = select(Business).where(Business.deleted_at.is_(None))
        if status:
            stmt = stmt.where(Business.status == status)
        return self.db.scalars(stmt.order_by(Business.opened_at.desc())).all()
