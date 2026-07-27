from __future__ import annotations

from datetime import datetime
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.businesses.models.business import Business
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    DocumentStatus,
    PermanentDocument,
    PermanentDocumentType,
)
from app.users.models.user import User
from tests.helpers.factory_utils import (
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory


class PermanentDocumentFactory:
    """Model-level PermanentDocument factory."""

    def __init__(self, db: Session, client_factory: ClientFactory, actor_user: User) -> None:
        self.db = db
        self.client_factory = client_factory
        self.actor_user = actor_user
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        scope: DocumentScope = DocumentScope.CLIENT,
        document_type: PermanentDocumentType = PermanentDocumentType.ID_COPY,
        storage_key: str | None = None,
        original_filename: str | None = None,
        file_size_bytes: int | None = None,
        mime_type: str | None = None,
        tax_year: int | None = None,
        is_present: bool = True,
        is_deleted: bool = False,
        status: DocumentStatus = DocumentStatus.PENDING,
        version: int = 1,
        superseded_by: int | None = None,
        annual_report_id: int | None = None,
        binder_id: int | None = None,
        uploaded_by: int | None = None,
        uploaded_at: datetime | None = None,
        approved_by: int | None = None,
        approved_at: datetime | None = None,
        rejected_by: int | None = None,
        rejected_at: datetime | None = None,
        commit: bool = False,
    ) -> PermanentDocument:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        resolve_exclusive(business, business_id, names="business or business_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        if uploaded_by is None:
            uploaded_by = self.actor_user.id
        document_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "scope": scope,
            "document_type": document_type,
            "storage_key": storage_key or f"test/documents/{sequence}.pdf",
            "original_filename": original_filename,
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type,
            "tax_year": tax_year,
            "is_present": is_present,
            "is_deleted": is_deleted,
            "status": status,
            "version": version,
            "superseded_by": superseded_by,
            "annual_report_id": annual_report_id,
            "binder_id": binder_id,
            "uploaded_by": uploaded_by,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "rejected_by": rejected_by,
            "rejected_at": rejected_at,
        }
        if uploaded_at is not None:
            document_fields["uploaded_at"] = uploaded_at
        document = PermanentDocument(**document_fields)
        self.db.add(document)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(document)
        return document
