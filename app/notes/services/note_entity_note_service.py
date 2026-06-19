from sqlalchemy.orm import Session

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import ForbiddenError, NotFoundError
from app.notes.models.note_entity_note import EntityNote
from app.notes.repositories.note_entity_note_repository import EntityNoteRepository
from app.users.repositories.user_repository import UserRepository

_NOT_FOUND = ErrorCode.NOTE_NOT_FOUND
_CLIENT_ENTITY_TYPE = "client"


class EntityNoteService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EntityNoteRepository(db)
        self.user_repo = UserRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def _assert_client_exists(self, client_id: int) -> None:
        if not self.client_repo.get_by_id(client_id):
            raise NotFoundError(
                f"רשומת לקוח {client_id} לא נמצאה", ErrorCode.CLIENT_RECORD_NOT_FOUND
            )

    def _attach_created_by_names(self, notes: list[EntityNote]) -> list[EntityNote]:
        user_ids = sorted({note.created_by for note in notes if note.created_by is not None})
        users_by_id = {user.id: user.full_name for user in self.user_repo.list_by_ids(user_ids)}
        for note in notes:
            note.created_by_name = (
                users_by_id.get(note.created_by) if note.created_by is not None else None
            )
        return notes

    def _attach_created_by_name(self, note: EntityNote) -> EntityNote:
        return self._attach_created_by_names([note])[0]

    def _get_or_raise(self, note_id: int, entity_type: str, entity_id: int) -> EntityNote:
        note = self.repo.get_by_id(note_id)
        if not note or note.entity_type != entity_type or note.entity_id != entity_id:
            raise NotFoundError(
                f"הערה {note_id} לא נמצאה",
                _NOT_FOUND,
            )
        return note

    def list_notes(
        self,
        entity_type: str,
        entity_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EntityNote], int]:
        if entity_type == _CLIENT_ENTITY_TYPE:
            self._assert_client_exists(entity_id)
        items, total = self.repo.list_for_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            page=page,
            page_size=page_size,
        )
        return self._attach_created_by_names(items), total

    def add_note(
        self,
        entity_type: str,
        entity_id: int,
        note: str,
        created_by: int | None = None,
    ) -> EntityNote:
        if entity_type == _CLIENT_ENTITY_TYPE:
            self._assert_client_exists(entity_id)
        note_obj = self.repo.create(
            entity_type=entity_type,
            entity_id=entity_id,
            note=note,
            created_by=created_by,
        )
        return self._attach_created_by_name(note_obj)

    def update_note(
        self,
        note_id: int,
        entity_type: str,
        entity_id: int,
        note: str,
        actor_id: int,
    ) -> EntityNote:
        obj = self._get_or_raise(note_id, entity_type, entity_id)
        if obj.created_by != actor_id:
            raise ForbiddenError("אין הרשאה לעדכן הערה זו", ErrorCode.NOTE_FORBIDDEN)
        updated = self.repo.update(note_id, note=note)
        if not updated:
            raise NotFoundError(f"הערה {note_id} לא נמצאה", _NOT_FOUND)
        return self._attach_created_by_name(updated)

    def delete_note(
        self,
        note_id: int,
        entity_type: str,
        entity_id: int,
        actor_id: int,
    ) -> None:
        self._get_or_raise(note_id, entity_type, entity_id)
        self.repo.soft_delete(note_id, deleted_by=actor_id)
