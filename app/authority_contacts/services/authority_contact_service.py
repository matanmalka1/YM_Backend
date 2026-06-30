from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_AUTHORITY_CONTACT_CREATED,
    ACTION_AUTHORITY_CONTACT_DELETED,
    ACTION_AUTHORITY_CONTACT_UPDATED,
    ENTITY_AUTHORITY_CONTACT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.authority_contacts.models.authority_contact import AuthorityContact, ContactType
from app.authority_contacts.repositories.authority_contact_repository import (
    AuthorityContactRepository,
)
from app.clients.services.client_service import get_client_or_raise
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError

_SYSTEM_ACTOR_DISPLAY = "מערכת"


class AuthorityContactService:
    """Authority contact management business logic."""

    def __init__(self, db: Session):
        self.db = db
        self.contact_repo = AuthorityContactRepository(db)
        self._audit = EntityAuditWriter(db)

    def _actor_kwargs(self, actor_id: int | None, actor_name: str | None) -> dict:
        if actor_id is None:
            return {
                "actor_type": "system",
                "actor_display_name": actor_name or _SYSTEM_ACTOR_DISPLAY,
            }
        return {"actor_display_name": actor_name}

    def _audit_snapshot(self, contact: AuthorityContact) -> dict:
        return {
            "contact_type": contact.contact_type,
            "name": contact.name,
            "office": contact.office,
            "phone": contact.phone,
            "email": contact.email,
            "notes": contact.notes,
        }

    def _audit_metadata(self, contact: AuthorityContact) -> dict:
        return {"client_record_id": contact.client_record_id, "contact_id": contact.id}

    def add_contact(
        self,
        client_record_id: int,
        contact_type: str,
        name: str,
        office: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> AuthorityContact:
        """Add new authority contact for client."""
        contact_type_enum = (
            contact_type if isinstance(contact_type, ContactType) else ContactType(contact_type)
        )
        get_client_or_raise(self.db, client_record_id)

        contact = self.contact_repo.create(
            client_record_id=client_record_id,
            contact_type=contact_type_enum,
            name=name,
            office=office,
            phone=phone,
            email=email,
            notes=notes,
        )
        self._audit.record_action(
            ENTITY_AUTHORITY_CONTACT,
            contact.id,
            actor_id,
            ACTION_AUTHORITY_CONTACT_CREATED,
            new_value=self._audit_snapshot(contact),
            metadata_json=self._audit_metadata(contact),
            **self._actor_kwargs(actor_id, actor_name),
        )
        return contact

    def update_contact(
        self,
        client_record_id: int,
        contact_id: int,
        actor_id: int | None = None,
        actor_name: str | None = None,
        **fields,
    ) -> AuthorityContact:
        """Update contact details, scoped to client_record_id."""
        if "contact_type" in fields:
            ct = fields["contact_type"]
            fields["contact_type"] = ct if isinstance(ct, ContactType) else ContactType(ct)

        existing = self.get_contact(client_record_id, contact_id)
        old_snapshot = self._audit_snapshot(existing)
        updated = self.contact_repo.update_for_client(client_record_id, contact_id, **fields)
        if not updated:
            raise NotFoundError(
                f"איש קשר {contact_id} לא נמצא", ErrorCode.AUTHORITY_CONTACT_NOT_FOUND
            )
        self._audit.record_action(
            ENTITY_AUTHORITY_CONTACT,
            updated.id,
            actor_id,
            ACTION_AUTHORITY_CONTACT_UPDATED,
            old_value=old_snapshot,
            new_value=self._audit_snapshot(updated),
            metadata_json=self._audit_metadata(updated),
            **self._actor_kwargs(actor_id, actor_name),
        )
        return updated

    def list_client_contacts(
        self,
        client_record_id: int,
        contact_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuthorityContact], int]:
        """List contacts for client with pagination."""
        contact_type_enum: ContactType | None = ContactType(contact_type) if contact_type else None
        get_client_or_raise(self.db, client_record_id)

        items = self.contact_repo.list_by_client_record(
            client_record_id, contact_type_enum, page=page, page_size=page_size
        )
        total = self.contact_repo.count_by_client_record(client_record_id, contact_type_enum)
        return items, total

    def delete_contact(
        self,
        client_record_id: int,
        contact_id: int,
        actor_id: int,
        actor_name: str | None = None,
    ) -> None:
        """Soft-delete contact, scoped to client_record_id."""
        contact = self.get_contact(client_record_id, contact_id)
        old_snapshot = self._audit_snapshot(contact)
        success = self.contact_repo.delete_for_client(
            client_record_id, contact_id, deleted_by=actor_id
        )
        if not success:
            raise NotFoundError(
                f"איש קשר {contact_id} לא נמצא", ErrorCode.AUTHORITY_CONTACT_NOT_FOUND
            )
        self._audit.record_action(
            ENTITY_AUTHORITY_CONTACT,
            contact_id,
            actor_id,
            ACTION_AUTHORITY_CONTACT_DELETED,
            old_value=old_snapshot,
            actor_display_name=actor_name,
            metadata_json=self._audit_metadata(contact),
        )

    def get_contact(self, client_record_id: int, contact_id: int) -> AuthorityContact:
        """Get contact by ID, scoped to client_record_id."""
        contact = self.contact_repo.get_for_client(client_record_id, contact_id)
        if not contact:
            raise NotFoundError(
                f"איש קשר {contact_id} לא נמצא", ErrorCode.AUTHORITY_CONTACT_NOT_FOUND
            )
        return contact
