from sqlalchemy.orm import Session

from app.authority_contacts.models.authority_contact import AuthorityContact, ContactType
from app.authority_contacts.repositories.authority_contact_repository import (
    AuthorityContactRepository,
)
from app.clients.services.client_service import get_client_or_raise
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class AuthorityContactService:
    """Authority contact management business logic."""

    def __init__(self, db: Session):
        self.db = db
        self.contact_repo = AuthorityContactRepository(db)

    def add_contact(
        self,
        client_record_id: int,
        contact_type: str,
        name: str,
        office: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        notes: str | None = None,
    ) -> AuthorityContact:
        """Add new authority contact for client."""
        contact_type_enum = (
            contact_type if isinstance(contact_type, ContactType) else ContactType(contact_type)
        )
        get_client_or_raise(self.db, client_record_id)

        return self.contact_repo.create(
            client_record_id=client_record_id,
            contact_type=contact_type_enum,
            name=name,
            office=office,
            phone=phone,
            email=email,
            notes=notes,
        )

    def update_contact(
        self,
        client_record_id: int,
        contact_id: int,
        **fields,
    ) -> AuthorityContact:
        """Update contact details, scoped to client_record_id."""
        if "contact_type" in fields:
            ct = fields["contact_type"]
            fields["contact_type"] = ct if isinstance(ct, ContactType) else ContactType(ct)

        updated = self.contact_repo.update_for_client(client_record_id, contact_id, **fields)
        if not updated:
            raise NotFoundError(
                f"איש קשר {contact_id} לא נמצא", ErrorCode.AUTHORITY_CONTACT_NOT_FOUND
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

    def delete_contact(self, client_record_id: int, contact_id: int, actor_id: int) -> None:
        """Soft-delete contact, scoped to client_record_id."""
        success = self.contact_repo.delete_for_client(
            client_record_id, contact_id, deleted_by=actor_id
        )
        if not success:
            raise NotFoundError(
                f"איש קשר {contact_id} לא נמצא", ErrorCode.AUTHORITY_CONTACT_NOT_FOUND
            )

    def get_contact(self, client_record_id: int, contact_id: int) -> AuthorityContact:
        """Get contact by ID, scoped to client_record_id."""
        contact = self.contact_repo.get_for_client(client_record_id, contact_id)
        if not contact:
            raise NotFoundError(
                f"איש קשר {contact_id} לא נמצא", ErrorCode.AUTHORITY_CONTACT_NOT_FOUND
            )
        return contact
