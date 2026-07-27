from __future__ import annotations

from datetime import datetime
from itertools import count
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.businesses.models.business import Business
from app.notifications.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from tests.helpers.factory_utils import (
    ClientRef,
    resolve_exclusive,
)

if TYPE_CHECKING:
    from tests.factories.clients import ClientFactory


class NotificationFactory:
    """Model-level Notification factory."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: ClientRef | None = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        binder_id: int | None = None,
        annual_report_id: int | None = None,
        signature_request_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        trigger: NotificationTrigger = NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel: NotificationChannel = NotificationChannel.EMAIL,
        recipient: str | None = None,
        content_snapshot: str = "Test notification",
        subject_snapshot: str | None = None,
        status: NotificationStatus = NotificationStatus.PENDING,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
        error_message: str | None = None,
        retry_count: int = 0,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        triggered_by: int | None = None,
        created_at: datetime | None = None,
        commit: bool = False,
    ) -> Notification:
        resolve_exclusive(client, client_record_id, names="client or client_record_id")
        resolve_exclusive(business, business_id, names="business or business_id")
        next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        notification_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "binder_id": binder_id,
            "annual_report_id": annual_report_id,
            "signature_request_id": signature_request_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "trigger": trigger,
            "channel": channel,
            "recipient": recipient,
            "content_snapshot": content_snapshot,
            "subject_snapshot": subject_snapshot,
            "status": status,
            "sent_at": sent_at,
            "failed_at": failed_at,
            "error_message": error_message,
            "retry_count": retry_count,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "triggered_by": triggered_by,
        }
        if created_at is not None:
            notification_fields["created_at"] = created_at
        notification = Notification(**notification_fields)
        self.db.add(notification)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(notification)
        return notification
