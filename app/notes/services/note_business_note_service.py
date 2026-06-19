"""Business-scoped note operations."""

from sqlalchemy.orm import Session

from app.businesses.repositories.business_repository import BusinessRepository
from app.businesses.business_guards import (
    assert_business_belongs_to_legal_entity,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.notes.models.note_entity_note import EntityNote
from app.notes.services.note_entity_note_service import EntityNoteService

_ENTITY_TYPE = "business"


class BusinessNoteService:
    def __init__(self, db: Session):
        self.business_repo = BusinessRepository(db)
        self.client_repo = ClientRecordRepository(db)
        self.note_service = EntityNoteService(db)

    def list_notes(
        self,
        client_id: int,
        business_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EntityNote], int]:
        self._assert_business_belongs_to_client(client_id, business_id)
        return self.note_service.list_notes(
            entity_type=_ENTITY_TYPE,
            entity_id=business_id,
            page=page,
            page_size=page_size,
        )

    def add_note(
        self,
        client_id: int,
        business_id: int,
        *,
        note: str,
        created_by: int,
    ) -> EntityNote:
        self._assert_business_belongs_to_client(client_id, business_id)
        return self.note_service.add_note(
            entity_type=_ENTITY_TYPE,
            entity_id=business_id,
            note=note,
            created_by=created_by,
        )

    def update_note(
        self,
        client_id: int,
        business_id: int,
        note_id: int,
        *,
        note: str,
        actor_id: int,
    ) -> EntityNote:
        self._assert_business_belongs_to_client(client_id, business_id)
        return self.note_service.update_note(
            note_id=note_id,
            entity_type=_ENTITY_TYPE,
            entity_id=business_id,
            note=note,
            actor_id=actor_id,
        )

    def delete_note(self, client_id: int, business_id: int, note_id: int, *, actor_id: int) -> None:
        self._assert_business_belongs_to_client(client_id, business_id)
        self.note_service.delete_note(
            note_id=note_id,
            entity_type=_ENTITY_TYPE,
            entity_id=business_id,
            actor_id=actor_id,
        )

    def _assert_business_belongs_to_client(self, client_id: int, business_id: int) -> None:
        business = self.business_repo.get_by_id(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", ErrorCode.BUSINESS_NOT_FOUND)
        record = self.client_repo.get_by_id(client_id)
        if not record:
            raise NotFoundError(
                f"רשומת לקוח {client_id} לא נמצאה", ErrorCode.CLIENT_RECORD_NOT_FOUND
            )
        assert_business_belongs_to_legal_entity(business, record.legal_entity_id)
