from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.communications.models.correspondence import Correspondence, CorrespondenceType
from app.utils.time_utils import utcnow_aware


class CorrespondenceRepository(BaseRepository[Correspondence]):
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        client_record_id: int,
        correspondence_type: CorrespondenceType,
        subject: str,
        occurred_at: datetime,
        created_by: int,
        business_id: int | None = None,  # OPTIONAL — UI grouping only
        contact_id: int | None = None,
        notes: str | None = None,
    ) -> Correspondence:
        entry = Correspondence(
            client_record_id=client_record_id,
            business_id=business_id,
            contact_id=contact_id,
            correspondence_type=correspondence_type,
            subject=subject,
            notes=notes,
            occurred_at=occurred_at,
            created_by=created_by,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        client_record_id: int | None = None,
        business_id: int | None = None,
        correspondence_type: CorrespondenceType | None = None,
        contact_id: int | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        order: Literal["asc", "desc"] = "desc",
    ) -> tuple[list[Correspondence], int]:
        filters = [Correspondence.deleted_at.is_(None)]
        if client_record_id is not None:
            filters.append(Correspondence.client_record_id == client_record_id)
        if business_id is not None:
            filters.append(Correspondence.business_id == business_id)
        if correspondence_type is not None:
            filters.append(Correspondence.correspondence_type == correspondence_type)
        if contact_id is not None:
            filters.append(Correspondence.contact_id == contact_id)
        if occurred_after is not None:
            filters.append(Correspondence.occurred_at >= occurred_after)
        if occurred_before is not None:
            filters.append(Correspondence.occurred_at <= occurred_before)

        total = self.db.scalar(select(func.count(Correspondence.id)).where(*filters)) or 0
        order_expr = (
            Correspondence.occurred_at.desc()
            if order == "desc"
            else Correspondence.occurred_at.asc()
        )
        stmt = self.apply_pagination(
            select(Correspondence).where(*filters).order_by(order_expr, Correspondence.id.desc()),
            page,
            page_size,
        )
        items = self.db.scalars(stmt).all()
        return items, total

    def list_by_client_paginated(
        self,
        client_record_id: int,
        *,
        page: int,
        page_size: int,
        business_id: int | None = None,
        correspondence_type: CorrespondenceType | None = None,
        contact_id: int | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        order: Literal["asc", "desc"] = "desc",
    ) -> tuple[list[Correspondence], int]:
        return self.list_paginated(
            client_record_id=client_record_id,
            business_id=business_id,
            page=page,
            page_size=page_size,
            correspondence_type=correspondence_type,
            contact_id=contact_id,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            order=order,
        )

    def get_by_id(self, entry_id: int) -> Correspondence | None:
        return self.db.scalars(
            select(Correspondence).where(
                Correspondence.id == entry_id, Correspondence.deleted_at.is_(None)
            )
        ).first()

    def update(self, entry_id: int, **fields) -> Correspondence | None:
        entry = self.get_by_id(entry_id)
        if not entry:
            return None
        for key, value in fields.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        self.db.flush()
        return entry

    def soft_delete(self, entry_id: int, deleted_by: int | None = None) -> bool:
        entry = self.get_by_id(entry_id)
        if not entry:
            return False
        entry.deleted_at = utcnow_aware()
        entry.deleted_by = deleted_by
        self.db.flush()
        return True
