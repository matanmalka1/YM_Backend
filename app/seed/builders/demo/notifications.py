from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random

from app.binders.models.binder import BinderLocationStatus
from app.notifications.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)

from ...data.demo_catalog import demo_email
from ..shared.client_refs import get_seed_client_record_id


def create_notifications(
    db, rng: Random, clients, businesses, binders, users=None, cfg=None
) -> None:
    current_year = cfg.reference_date.year if cfg else None
    clients_by_id = {c.id: c for c in clients}
    businesses_by_client: dict[int, list] = {}
    for business in businesses:
        businesses_by_client.setdefault(get_seed_client_record_id(business), []).append(business)

    for binder in binders:
        if rng.random() > 0.65:
            continue
        binder_client_record_id = get_seed_client_record_id(binder)
        candidate_businesses = businesses_by_client.get(binder_client_record_id, [])
        if not candidate_businesses:
            continue
        business = rng.choice(candidate_businesses)
        business_client_record_id = get_seed_client_record_id(business)
        client = clients_by_id.get(business_client_record_id)
        if not client:
            continue

        is_email = rng.random() < 0.35
        channel = NotificationChannel.EMAIL if is_email else NotificationChannel.WHATSAPP
        recipient = (
            getattr(client, "email", None)
            if is_email
            else (getattr(client, "phone", None) or "0500000000")
        )
        if not recipient:
            recipient = demo_email("client", client.id)

        if binder.location_status == BinderLocationStatus.READY_FOR_HANDOVER:
            trigger = NotificationTrigger.BINDER_READY_FOR_HANDOVER
        else:
            trigger = rng.choice(
                [
                    NotificationTrigger.BINDER_MISSING_DOCUMENTS,
                    NotificationTrigger.CLIENT_GENERAL_MESSAGE,
                ]
            )

        created_at = datetime.now(UTC) - timedelta(days=rng.randint(0, 60))
        is_old = current_year is not None and created_at.year < current_year
        if is_old:
            status = NotificationStatus.SENT
        else:
            status = rng.choices(
                [
                    NotificationStatus.SENT,
                    NotificationStatus.PENDING,
                    NotificationStatus.FAILED,
                    NotificationStatus.SKIPPED,
                ],
                weights=[70, 15, 10, 5],
                k=1,
            )[0]
        sent_at = None
        failed_at = None
        if status == NotificationStatus.SENT:
            sent_at = min(
                datetime.now(UTC),
                created_at + timedelta(days=rng.randint(0, 5), hours=rng.randint(0, 12)),
            )
        elif status == NotificationStatus.FAILED:
            failed_at = min(
                datetime.now(UTC),
                created_at + timedelta(days=rng.randint(0, 3), hours=rng.randint(0, 12)),
            )

        triggered_by = None
        if trigger == NotificationTrigger.CLIENT_GENERAL_MESSAGE and users:
            triggered_by = rng.choice(users).id

        notification = Notification(
            client_record_id=business_client_record_id,
            business_id=business.id,
            binder_id=binder.id,
            trigger=trigger,
            channel=channel,
            status=status,
            recipient=recipient if status != NotificationStatus.SKIPPED else None,
            content_snapshot=f"הודעה אוטומטית עבור קלסר {binder.binder_number}",
            sent_at=sent_at,
            failed_at=failed_at,
            error_message="פסק זמן מול הספק" if status == NotificationStatus.FAILED else None,
            triggered_by=triggered_by,
            created_at=created_at,
        )
        db.add(notification)

    db.flush()
