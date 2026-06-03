from __future__ import annotations

import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.notification.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.utils.time_utils import utcnow


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        client_record_id: int,
        trigger: NotificationTrigger,
        channel: NotificationChannel,
        content_snapshot: str,
        recipient: str | None = None,
        subject_snapshot: str | None = None,
        business_id: int | None = None,
        binder_id: int | None = None,
        annual_report_id: int | None = None,
        signature_request_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        triggered_by: int | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        status: NotificationStatus = NotificationStatus.PENDING,
    ) -> Notification:
        notification = Notification(
            client_record_id=client_record_id,
            business_id=business_id,
            binder_id=binder_id,
            annual_report_id=annual_report_id,
            signature_request_id=signature_request_id,
            entity_type=entity_type,
            entity_id=entity_id,
            trigger=trigger,
            channel=channel,
            recipient=recipient,
            content_snapshot=content_snapshot,
            subject_snapshot=subject_snapshot,
            status=status,
            triggered_by=triggered_by,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        self.db.add(notification)
        self.db.flush()
        return notification

    def mark_sent(self, notification_id: int) -> Notification | None:
        notification = self.get_by_id(notification_id)
        if not notification:
            return None
        notification.status = NotificationStatus.SENT
        notification.sent_at = utcnow()
        self.db.flush()
        return notification

    def mark_failed(self, notification_id: int, error_message: str) -> Notification | None:
        notification = self.get_by_id(notification_id)
        if not notification:
            return None
        notification.status = NotificationStatus.FAILED
        notification.failed_at = utcnow()
        notification.error_message = error_message
        self.db.flush()
        return notification

    def get_by_id(self, notification_id: int) -> Notification | None:
        return self.db.scalars(
            select(Notification).where(Notification.id == notification_id)
        ).first()

    def find_by_idempotency_key(
        self,
        key: str,
        ttl_hours: int = 24,
    ) -> Notification | None:
        """Return most recent record with this key within TTL. Caller compares request_hash."""
        cutoff = utcnow() - datetime.timedelta(hours=ttl_hours)
        return self.db.scalars(
            select(Notification)
            .where(
                Notification.idempotency_key == key,
                Notification.created_at >= cutoff,
            )
            .order_by(Notification.created_at.desc())
        ).first()

    def list_paginated(
        self,
        page: int = 1,
        page_size: int = 25,
        client_record_id: int | None = None,
        business_id: int | None = None,
        status: NotificationStatus | None = None,
        statuses: list[NotificationStatus] | None = None,
        trigger: NotificationTrigger | None = None,
        channel: NotificationChannel | None = None,
        triggered_by: int | None = None,
        date_from: datetime.datetime | None = None,
        date_to: datetime.datetime | None = None,
    ) -> tuple[list[Notification], int]:
        count_stmt = select(func.count(Notification.id))
        list_stmt = select(Notification)

        filters = []
        if client_record_id is not None:
            filters.append(Notification.client_record_id == client_record_id)
        if business_id is not None:
            filters.append(Notification.business_id == business_id)
        if status is not None:
            filters.append(Notification.status == status)
        if statuses is not None:
            filters.append(Notification.status.in_(statuses))
        if trigger is not None:
            filters.append(Notification.trigger == trigger)
        if channel is not None:
            filters.append(Notification.channel == channel)
        if triggered_by is not None:
            filters.append(Notification.triggered_by == triggered_by)
        if date_from is not None:
            filters.append(Notification.created_at >= date_from)
        if date_to is not None:
            filters.append(Notification.created_at <= date_to)

        if filters:
            count_stmt = count_stmt.where(*filters)
            list_stmt = list_stmt.where(*filters)

        total = self.db.scalar(count_stmt) or 0
        items = self.db.scalars(
            list_stmt.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def count_by_status(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
    ) -> dict[str, int]:
        stmt = select(Notification.status, func.count(Notification.id)).group_by(
            Notification.status
        )
        if client_record_id is not None:
            stmt = stmt.where(Notification.client_record_id == client_record_id)
        if business_id is not None:
            stmt = stmt.where(Notification.business_id == business_id)
        rows = self.db.execute(stmt).all()
        result: dict[str, int] = {s.value: 0 for s in NotificationStatus}
        result["total"] = 0
        for status_val, count in rows:
            key = (
                status_val.value if isinstance(status_val, NotificationStatus) else str(status_val)
            )
            result[key] = count
            result["total"] += count
        return result

    def get_last_for_binder_trigger(
        self, binder_id: int, trigger: NotificationTrigger
    ) -> Notification | None:
        return self.db.scalars(
            select(Notification)
            .where(Notification.binder_id == binder_id, Notification.trigger == trigger)
            .order_by(Notification.created_at.desc())
        ).first()

    def get_last_for_annual_report_trigger(
        self, annual_report_id: int, trigger: NotificationTrigger
    ) -> Notification | None:
        return self.db.scalars(
            select(Notification)
            .where(
                Notification.annual_report_id == annual_report_id,
                Notification.trigger == trigger,
            )
            .order_by(Notification.created_at.desc())
        ).first()

    def get_last_for_entity_trigger(
        self, entity_id: int, trigger: NotificationTrigger
    ) -> Notification | None:
        """Last notification for a generic entity_id + trigger."""
        return self.db.scalars(
            select(Notification)
            .where(Notification.entity_id == entity_id, Notification.trigger == trigger)
            .order_by(Notification.created_at.desc())
        ).first()

    def get_last_for_signature_trigger(
        self, signature_request_id: int, trigger: NotificationTrigger
    ) -> Notification | None:
        return self.db.scalars(
            select(Notification)
            .where(
                Notification.signature_request_id == signature_request_id,
                Notification.trigger == trigger,
            )
            .order_by(Notification.created_at.desc())
        ).first()

    def latest_by_binder_ids(
        self, binder_ids: list[int], trigger: NotificationTrigger
    ) -> dict[int, Notification]:
        if not binder_ids:
            return {}
        ranked = (
            select(
                Notification.id.label("id"),
                Notification.binder_id.label("binder_id"),
                func.row_number()
                .over(
                    partition_by=Notification.binder_id,
                    order_by=(Notification.created_at.desc(), Notification.id.desc()),
                )
                .label("rn"),
            )
            .where(
                Notification.binder_id.in_(binder_ids),
                Notification.trigger == trigger,
            )
            .subquery()
        )
        rows = self.db.scalars(
            select(Notification)
            .join(ranked, ranked.c.id == Notification.id)
            .where(ranked.c.rn == 1)
        ).all()
        return {row.binder_id: row for row in rows if row.binder_id is not None}

    def latest_by_annual_report_ids(
        self, annual_report_ids: list[int], trigger: NotificationTrigger
    ) -> dict[int, Notification]:
        if not annual_report_ids:
            return {}
        ranked = (
            select(
                Notification.id.label("id"),
                Notification.annual_report_id.label("annual_report_id"),
                func.row_number()
                .over(
                    partition_by=Notification.annual_report_id,
                    order_by=(Notification.created_at.desc(), Notification.id.desc()),
                )
                .label("rn"),
            )
            .where(
                Notification.annual_report_id.in_(annual_report_ids),
                Notification.trigger == trigger,
            )
            .subquery()
        )
        rows = self.db.scalars(
            select(Notification)
            .join(ranked, ranked.c.id == Notification.id)
            .where(ranked.c.rn == 1)
        ).all()
        return {row.annual_report_id: row for row in rows if row.annual_report_id is not None}
