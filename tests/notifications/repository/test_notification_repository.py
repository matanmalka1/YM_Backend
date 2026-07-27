from datetime import date

from sqlalchemy import select

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.repositories.notification_repository import NotificationRepository


def _business(create_client_with_business, suffix: str) -> Business:
    _, business = create_client_with_business(
        full_name=f"Notif Repo Client {suffix}",
        id_number=f"7100000{suffix}",
        id_number_type=IdNumberType.CORPORATION,
        business_name=f"Notif Repo Biz {suffix}",
        opened_at=date(2024, 1, 1),
        create_person=False,
    )
    return business


def _client_record_id(test_db, business: Business) -> int:
    return test_db.scalar(
        select(ClientRecord.id).filter(ClientRecord.legal_entity_id == business.legal_entity_id)
    )


def test_notification_repository_lifecycle(test_db, create_client_with_business, actor_user):
    repo = NotificationRepository(test_db)
    business = _business(create_client_with_business, "1")
    cr_id = _client_record_id(test_db, business)

    pending = repo.create(
        client_record_id=cr_id,
        business_id=business.id,
        trigger=NotificationTrigger.BINDER_MISSING_DOCUMENTS,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="Missing docs",
        subject_snapshot="Subject",
        triggered_by=actor_user.id,
    )
    later = repo.create(
        client_record_id=cr_id,
        business_id=business.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.WHATSAPP,
        recipient="0501111111",
        content_snapshot="General message",
    )

    assert pending.triggered_by == actor_user.id
    assert pending.status == NotificationStatus.PENDING

    sent = repo.mark_sent(pending.id)
    assert sent.status == NotificationStatus.SENT
    assert sent.sent_at is not None

    failed = repo.mark_failed(later.id, error_message="delivery error")
    assert failed.status == NotificationStatus.FAILED
    assert failed.failed_at is not None
    assert failed.error_message == "delivery error"

    ordered, total = repo.list_paginated(business_id=business.id)
    assert [n.id for n in ordered] == [later.id, pending.id]
    assert total == 2

    assert repo.get_by_id(pending.id) is not None
    assert repo.mark_sent(notification_id=9999) is None
    assert repo.mark_failed(notification_id=9999, error_message="x") is None


def test_skipped_record_created_via_create_with_status(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "sk1")
    cr_id = _client_record_id(test_db, b)

    skipped = repo.create(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient=None,
        content_snapshot="skipped content",
        status=NotificationStatus.SKIPPED,
    )
    assert skipped.status == NotificationStatus.SKIPPED
    assert skipped.recipient is None


def test_find_by_idempotency_key(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "idem1")
    cr_id = _client_record_id(test_db, b)

    n = repo.create(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="body",
        idempotency_key="key-abc",
        request_hash="hash-abc",
    )
    repo.mark_sent(n.id)

    found = repo.find_by_idempotency_key("key-abc")
    assert found is not None
    assert found.id == n.id

    not_found = repo.find_by_idempotency_key("key-nonexistent")
    assert not_found is None


def test_notification_repository_pagination(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b1 = _business(create_client_with_business, "2")
    b2 = _business(create_client_with_business, "3")

    repo.create(
        client_record_id=_client_record_id(test_db, b1),
        business_id=b1.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@example.com",
        content_snapshot="a",
    )
    n2 = repo.create(
        client_record_id=_client_record_id(test_db, b1),
        business_id=b1.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@example.com",
        content_snapshot="b",
    )
    repo.create(
        client_record_id=_client_record_id(test_db, b2),
        business_id=b2.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="b@example.com",
        content_snapshot="c",
    )

    items, total = repo.list_paginated(page=1, page_size=1, business_id=b1.id)
    assert total == 2
    assert len(items) == 1
    assert items[0].id == n2.id

    global_items, global_total = repo.list_paginated(page=1, page_size=10)
    assert global_total == 3
    assert len(global_items) == 3


def test_list_paginated_filters_by_status(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "fs1")
    cr_id = _client_record_id(test_db, b)

    n_pending = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="pending",
    )
    n_sent = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="sent",
    )
    repo.mark_sent(n_sent.id)

    items, total = repo.list_paginated(business_id=b.id, status=NotificationStatus.PENDING)
    assert total == 1
    assert items[0].id == n_pending.id


def test_list_paginated_filters_by_trigger(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "ft1")
    cr_id = _client_record_id(test_db, b)

    n_msg = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="general",
    )
    repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.BINDER_MISSING_DOCUMENTS,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="binder",
    )

    items, total = repo.list_paginated(
        business_id=b.id, trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE
    )
    assert total == 1
    assert items[0].id == n_msg.id


def test_list_paginated_filters_by_channel(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "fc1")
    cr_id = _client_record_id(test_db, b)

    n_email = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="email",
    )
    repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.WHATSAPP,
        recipient="0501111111",
        content_snapshot="wa",
    )

    items, total = repo.list_paginated(business_id=b.id, channel=NotificationChannel.EMAIL)
    assert total == 1
    assert items[0].id == n_email.id


def test_count_by_status_returns_correct_counts(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "cs1")
    cr_id = _client_record_id(test_db, b)

    n_sent = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="s",
    )
    repo.mark_sent(n_sent.id)

    n_failed = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="f",
    )
    repo.mark_failed(n_failed.id, "err")

    repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="p",
    )

    counts = repo.count_by_status(business_id=b.id)
    assert counts["sent"] == 1
    assert counts["failed"] == 1
    assert counts["pending"] == 1
    assert counts["total"] == 3


def test_count_by_status_returns_zero_for_absent_statuses(test_db, create_client_with_business):
    repo = NotificationRepository(test_db)
    b = _business(create_client_with_business, "cs2")
    cr_id = _client_record_id(test_db, b)

    n = repo.create(
        client_record_id=cr_id,
        business_id=b.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel=NotificationChannel.EMAIL,
        recipient="a@x.com",
        content_snapshot="sent-only",
    )
    repo.mark_sent(n.id)

    counts = repo.count_by_status(business_id=b.id)
    assert counts["pending"] == 0
    assert counts["failed"] == 0
    assert counts["sent"] == 1
    assert counts["total"] == 1
