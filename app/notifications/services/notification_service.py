from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.models.client_record import ClientRecord
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.core.logging_config import get_logger
from app.legal_entities.models.legal_entity import LegalEntity
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import (
    NotificationListItem,
    NotificationPreviewRequest,
    NotificationPreviewResponse,
    NotificationResponse,
    NotificationResult,
    NotificationSendRequest,
    NotificationSummaryResponse,
)
from app.notifications.services.notification_send_service import NotificationSendService

logger = get_logger(__name__)


def _trigger_labels(notification: object) -> tuple[str, str]:
    from app.notifications.models.notification import TRIGGER_DOMAIN, TRIGGER_LABELS

    trigger = notification.trigger  # type: ignore[attr-defined]
    return (
        TRIGGER_LABELS.get(trigger, trigger.value),
        TRIGGER_DOMAIN.get(trigger, ""),
    )


def _enrich(
    notification: object,
    business_name_map: dict[int, str],
    client_name_map: dict[int, str],
) -> NotificationResponse:
    resp = NotificationResponse.model_validate(notification)
    resp.client_name = client_name_map.get(notification.client_record_id)  # type: ignore[attr-defined]
    if notification.business_id is not None:  # type: ignore[attr-defined]
        resp.business_name = business_name_map.get(notification.business_id)  # type: ignore[attr-defined]
    resp.trigger_label, resp.domain_label = _trigger_labels(notification)
    return resp


def _enrich_list_item(
    notification: object,
    business_name_map: dict[int, str],
    client_name_map: dict[int, str],
) -> NotificationListItem:
    item = NotificationListItem.model_validate(notification)
    item.client_name = client_name_map.get(notification.client_record_id)  # type: ignore[attr-defined]
    if notification.business_id is not None:  # type: ignore[attr-defined]
        item.business_name = business_name_map.get(notification.business_id)  # type: ignore[attr-defined]
    item.trigger_label, item.domain_label = _trigger_labels(notification)
    return item


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = NotificationRepository(db)
        self.business_repo = BusinessRepository(db)
        self._send_svc = NotificationSendService(db)

    # ── Preview / Send (delegates to NotificationSendService) ─────────────────

    def preview(
        self,
        request: NotificationPreviewRequest,
        triggered_by: int,
    ) -> NotificationPreviewResponse:
        return self._send_svc.preview(request, triggered_by=triggered_by)

    def send(
        self,
        request: NotificationSendRequest,
        triggered_by: int,
        idempotency_key: str,
    ) -> NotificationResult:
        return self._send_svc.send(
            request,
            triggered_by=triggered_by,
            idempotency_key=idempotency_key,
        )

    # ── Read / list ───────────────────────────────────────────────────────────

    def list_paginated(
        self,
        page: int = 1,
        page_size: int = 25,
        client_record_id: int | None = None,
        business_id: int | None = None,
        status: NotificationStatus | None = None,
        trigger: NotificationTrigger | None = None,
        channel: NotificationChannel | None = None,
        triggered_by: int | None = None,
        created_after: object | None = None,
        created_before: object | None = None,
    ) -> tuple[list[NotificationListItem], int]:
        items, total = self.repo.list_paginated(
            page=page,
            page_size=page_size,
            client_record_id=client_record_id,
            business_id=business_id,
            status=status,
            trigger=trigger,
            channel=channel,
            triggered_by=triggered_by,
            created_after=created_after,
            created_before=created_before,
        )
        business_name_map = self._build_business_name_map(items)
        client_name_map = self._build_client_name_map(items)
        return [_enrich_list_item(n, business_name_map, client_name_map) for n in items], total

    def get_detail(self, notification_id: int) -> NotificationResponse:
        notification = self.repo.get_by_id(notification_id)
        if notification is None:
            raise AppError(
                "ההודעה המבוקשת לא נמצאה",
                ErrorCode.NOTIFICATION_NOT_FOUND,
                status_code=404,
            )
        business_name_map = self._build_business_name_map([notification])
        client_name_map = self._build_client_name_map([notification])
        return _enrich(notification, business_name_map, client_name_map)

    def get_summary(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
    ) -> NotificationSummaryResponse:
        counts = self.repo.count_by_status(
            client_record_id=client_record_id,
            business_id=business_id,
        )
        return NotificationSummaryResponse(**counts)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_client_name_map(self, notifications: list) -> dict[int, str]:
        ids = list({n.client_record_id for n in notifications})  # type: ignore[attr-defined]
        if not ids:
            return {}
        rows = self.db.execute(
            select(ClientRecord.id, LegalEntity.official_name)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.id.in_(ids))
        ).all()
        return {row[0]: row[1] for row in rows}

    def _build_business_name_map(self, notifications: list) -> dict[int, str]:
        ids = [n.business_id for n in notifications if n.business_id is not None]  # type: ignore[attr-defined]
        if not ids:
            return {}
        businesses = self.business_repo.list_by_ids(list(set(ids)))
        return {
            b.id: getattr(b, "business_name", None) or getattr(b, "full_name", None)
            for b in businesses
        }
