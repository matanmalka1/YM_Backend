from datetime import datetime

from sqlalchemy.orm import Session

from app.authority_contact.repositories.authority_contact_repository import (
    AuthorityContactRepository,
)
from app.businesses.repositories.business_repository import BusinessRepository
from app.businesses.services.business_guards import (
    assert_business_belongs_to_legal_entity,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import ForbiddenError, NotFoundError
from app.communications.models.correspondence import Correspondence, CorrespondenceType
from app.communications.repositories.correspondence_repository import (
    CorrespondenceRepository,
)

_NOT_FOUND = "CORRESPONDENCE.NOT_FOUND"
_FORBIDDEN_CONTACT = "CORRESPONDENCE.FORBIDDEN_CONTACT"


class CorrespondenceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CorrespondenceRepository(db)
        self.contact_repo = AuthorityContactRepository(db)
        self.business_repo = BusinessRepository(db)

    def _assert_business_belongs_to_client(self, business_id: int, legal_entity_id: int) -> None:
        """Validate optional business context belongs to the same client."""
        business = self.business_repo.get_by_id(business_id)
        if not business:
            raise NotFoundError(f"עסק {business_id} לא נמצא", "BUSINESS.NOT_FOUND")
        assert_business_belongs_to_legal_entity(business, legal_entity_id)

    def _get_client_record_or_raise(self, client_record_id: int):
        record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if not record:
            raise NotFoundError(f"רשומת לקוח {client_record_id} לא נמצאה", "CLIENT.NOT_FOUND")
        return record

    def _assert_contact_belongs_to_client(self, contact_id: int, client_record_id: int) -> None:
        """
        authority_contacts belong to a CLIENT (not a business).
        Validate against client_record_id — not business_id.
        """
        contact = self.contact_repo.get_by_id(contact_id)
        if not contact or contact.client_record_id != client_record_id:
            raise ForbiddenError(
                f"איש קשר {contact_id} אינו שייך ללקוח {client_record_id}",
                _FORBIDDEN_CONTACT,
            )

    def _get_entry_or_raise(self, entry_id: int, client_record_id: int) -> Correspondence:
        """Fetch entry and verify it belongs to the given client."""
        entry = self.repo.get_by_id(entry_id)
        if not entry or entry.client_record_id != client_record_id:
            raise NotFoundError(
                f"התכתבות {entry_id} לא נמצאה עבור לקוח {client_record_id}",
                _NOT_FOUND,
            )
        return entry

    # ── Write operations ──────────────────────────────────────────────────────

    def add_entry(
        self,
        client_record_id: int,
        correspondence_type: CorrespondenceType,
        subject: str,
        occurred_at: datetime,
        created_by: int,
        business_id: int | None = None,
        contact_id: int | None = None,
        notes: str | None = None,
    ) -> Correspondence:
        client_record = self._get_client_record_or_raise(client_record_id)
        if business_id is not None:
            self._assert_business_belongs_to_client(business_id, client_record.legal_entity_id)

        if contact_id is not None:
            self._assert_contact_belongs_to_client(contact_id, client_record_id)

        return self.repo.create(
            client_record_id=client_record.id,
            business_id=business_id,
            correspondence_type=correspondence_type,
            subject=subject,
            occurred_at=occurred_at,
            created_by=created_by,
            contact_id=contact_id,
            notes=notes,
        )

    def get_entry(self, entry_id: int, client_record_id: int) -> Correspondence:
        self._get_client_record_or_raise(client_record_id)
        return self._get_entry_or_raise(entry_id, client_record_id)

    def update_entry(self, entry_id: int, client_record_id: int, **fields) -> Correspondence:
        client_record = self._get_client_record_or_raise(client_record_id)
        entry = self._get_entry_or_raise(entry_id, client_record_id)

        business_id = fields.get("business_id", entry.business_id)
        if business_id is not None:
            self._assert_business_belongs_to_client(business_id, client_record.legal_entity_id)

        contact_id = fields.get("contact_id", entry.contact_id)
        if contact_id is not None:
            self._assert_contact_belongs_to_client(contact_id, client_record_id)

        updated = self.repo.update(entry_id, **fields)
        if not updated:
            raise NotFoundError(
                f"התכתבות {entry_id} לא נמצאה עבור לקוח {client_record_id}",
                _NOT_FOUND,
            )
        return updated

    def delete_entry(self, entry_id: int, client_record_id: int, actor_id: int) -> None:
        self._get_client_record_or_raise(client_record_id)
        self._get_entry_or_raise(entry_id, client_record_id)
        self.repo.soft_delete(entry_id, deleted_by=actor_id)

    def list_client_entries(
        self,
        client_record_id: int,
        *,
        page: int,
        page_size: int,
        business_id: int | None = None,
        correspondence_type: CorrespondenceType | None = None,
        contact_id: int | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        order: str = "desc",
    ) -> tuple[list[Correspondence], int]:
        """All correspondence for a client, optionally filtered by business context."""
        client_record = self._get_client_record_or_raise(client_record_id)
        if business_id is not None:
            self._assert_business_belongs_to_client(business_id, client_record.legal_entity_id)
        return self.repo.list_by_client_record_paginated(
            client_record.id,
            business_id=business_id,
            page=page,
            page_size=page_size,
            correspondence_type=correspondence_type,
            contact_id=contact_id,
            from_date=from_date,
            to_date=to_date,
            order=order,
        )
