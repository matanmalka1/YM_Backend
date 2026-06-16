from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.notes.models.entity_note import EntityNote
from app.utils.time_utils import utcnow_aware


class EntityNoteRepository(BaseRepository[EntityNote]):
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        entity_type: str,
        entity_id: int,
        note: str,
        created_by: int | None = None,
    ) -> EntityNote:
        obj = EntityNote(
            entity_type=entity_type,
            entity_id=entity_id,
            note=note,
            created_by=created_by,
        )
        self.db.add(obj)
        self.db.flush()
        return obj

    def list_for_entity(
        self,
        entity_type: str,
        entity_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EntityNote], int]:
        base_where = [
            EntityNote.entity_type == entity_type,
            EntityNote.entity_id == entity_id,
            EntityNote.deleted_at.is_(None),
        ]
        total = self.db.scalar(select(func.count(EntityNote.id)).where(*base_where)) or 0
        stmt = self.apply_pagination(
            select(EntityNote).where(*base_where).order_by(EntityNote.created_at.desc()),
            page,
            page_size,
        )
        items = self.db.scalars(stmt).all()
        return items, total

    def get_by_id(self, note_id: int) -> EntityNote | None:
        return self.db.scalars(
            select(EntityNote).where(EntityNote.id == note_id, EntityNote.deleted_at.is_(None))
        ).first()

    def update(self, note_id: int, **fields) -> EntityNote | None:
        obj = self.get_by_id(note_id)
        if not obj:
            return None
        if "note" in fields:
            obj.note = fields["note"]
        self.db.flush()
        return obj

    def soft_delete(self, note_id: int, deleted_by: int | None = None) -> bool:
        obj = self.get_by_id(note_id)
        if not obj:
            return False
        obj.deleted_at = utcnow_aware()
        obj.deleted_by = deleted_by
        self.db.flush()
        return True
