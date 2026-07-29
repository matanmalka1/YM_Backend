from __future__ import annotations

from datetime import datetime
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.businesses.models.business import Business
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.users.models.user import User
from tests.helpers.factory_utils import (
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory


class SignatureRequestFactory:
    """Model-level SignatureRequest factory."""

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
        created_by: int | None = None,
        document_id: int | None = None,
        request_type: SignatureRequestType = SignatureRequestType.CUSTOM,
        title: str | None = None,
        description: str | None = None,
        content_hash: str | None = None,
        storage_key: str | None = None,
        signer_name: str = "Test Signer",
        signer_email: str | None = None,
        signer_phone: str | None = None,
        status: SignatureRequestStatus = SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        sent_at: datetime | None = None,
        expires_at: datetime | None = None,
        expiry_days: int = 14,
        signed_at: datetime | None = None,
        declined_at: datetime | None = None,
        canceled_at: datetime | None = None,
        canceled_by: int | None = None,
        signer_ip_address: str | None = None,
        signer_user_agent: str | None = None,
        decline_reason: str | None = None,
        signed_document_key: str | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> SignatureRequest:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        resolve_exclusive(business, business_id, names="business or business_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        if created_by is None:
            created_by = self.actor_user.id
        request_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "created_by": created_by,
            "document_id": document_id,
            "request_type": request_type,
            "title": title or f"Test Signature Request {sequence}",
            "description": description,
            "content_hash": content_hash,
            "storage_key": storage_key,
            "signer_name": signer_name,
            "signer_email": signer_email,
            "signer_phone": signer_phone,
            "status": status,
            "signing_token": signing_token,
            "updated_at": updated_at,
            "sent_at": sent_at,
            "expires_at": expires_at,
            "expiry_days": expiry_days,
            "signed_at": signed_at,
            "declined_at": declined_at,
            "canceled_at": canceled_at,
            "canceled_by": canceled_by,
            "signer_ip_address": signer_ip_address,
            "signer_user_agent": signer_user_agent,
            "decline_reason": decline_reason,
            "signed_document_key": signed_document_key,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            request_fields["created_at"] = created_at
        request = SignatureRequest(**request_fields)
        self.db.add(request)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(request)
        return request
