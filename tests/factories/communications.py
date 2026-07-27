from __future__ import annotations

from datetime import datetime
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.authority_contacts.models.authority_contact import AuthorityContact, ContactType
from tests.helpers.factory_utils import (
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory


class AuthorityContactFactory:
    """Model-level AuthorityContact factory."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        contact_type: ContactType = ContactType.OTHER,
        name: str | None = None,
        office: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> AuthorityContact:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        contact_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "contact_type": contact_type,
            "name": name or f"Test Authority Contact {sequence}",
            "office": office,
            "phone": phone,
            "email": email,
            "notes": notes,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            contact_fields["created_at"] = created_at
        contact = AuthorityContact(**contact_fields)
        self.db.add(contact)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(contact)
        return contact
