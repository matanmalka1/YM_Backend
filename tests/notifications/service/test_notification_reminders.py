"""Tests for NotificationSendService — skipped, policy, and preview behavior."""

import pytest

from app.clients.client_enums import ClientStatus
from app.notifications.models.notification import NotificationStatus, NotificationTrigger
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import (
    NotificationPreviewRequest,
    NotificationSendRequest,
)
from app.notifications.services.notification_send_service import NotificationSendService


def test_send_creates_skipped_record_when_no_email(test_db, client_factory, actor_user):
    cr_id = client_factory(email=None).id
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "נושא", "body": "גוף"},
    )
    result = svc.send(
        req,
        triggered_by=actor_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000201",
    )

    assert result.status == "skipped"
    assert result.notification_id is not None

    items, total = NotificationRepository(test_db).list_paginated(client_record_id=cr_id)
    assert total == 1
    assert items[0].status == NotificationStatus.SKIPPED
    assert items[0].recipient is None


def test_send_blocked_for_frozen_client_no_record(test_db, client_factory, actor_user):
    cr_id = client_factory(email="frozen@test.com", status=ClientStatus.FROZEN).id
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "נושא", "body": "גוף"},
    )
    result = svc.send(
        req,
        triggered_by=actor_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000202",
    )

    assert result.status == "blocked"
    assert result.notification_id is None

    _, total = NotificationRepository(test_db).list_paginated(client_record_id=cr_id)
    assert total == 0


def test_send_allowed_for_frozen_client_with_exempt_trigger(test_db, client_factory, actor_user):
    cr_id = client_factory(email="frozen-exempt@test.com", status=ClientStatus.FROZEN).id
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_MISSING_INFORMATION,
        overrides={"subject": "נושא", "body": "גוף"},
    )
    result = svc.send(
        req,
        triggered_by=actor_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000203",
    )

    # Should proceed (skipped due to stub delivery, not blocked)
    assert result.status in ("sent", "skipped", "failed")
    assert result.status != "blocked"


def test_send_validates_empty_subject(test_db, client_factory, actor_user):
    cr_id = client_factory(email="val@test.com").id
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "   ", "body": "גוף"},
    )
    from app.core.exceptions import AppError

    with pytest.raises(AppError) as exc:
        svc.send(
            req,
            triggered_by=actor_user.id,
            idempotency_key="00000000-0000-4000-8000-000000000204",
        )
    assert "נושא" in exc.value.message


def test_send_validates_visible_placeholder(test_db, client_factory, actor_user):
    cr_id = client_factory(email="ph@test.com").id
    svc = NotificationSendService(test_db)

    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "שלום", "body": "הי {client_name} צריך לבדוק"},
    )
    from app.core.exceptions import AppError

    with pytest.raises(AppError) as exc:
        svc.send(
            req,
            triggered_by=actor_user.id,
            idempotency_key="00000000-0000-4000-8000-000000000205",
        )
    assert "שדות" in exc.value.message


def test_preview_returns_ready_for_active_client(test_db, client_factory, actor_user):
    cr_id = client_factory(email="preview@test.com").id
    svc = NotificationSendService(test_db)

    req = NotificationPreviewRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
    )
    result = svc.preview(req, triggered_by=actor_user.id)

    assert result.can_send is True
    assert result.status == "ready"
    assert result.subject is not None
    assert result.body is not None
    assert result.recipient == "preview@test.com"


def test_preview_returns_blocked_for_frozen_client(test_db, client_factory, actor_user):
    cr_id = client_factory(email="frz-prev@test.com", status=ClientStatus.FROZEN).id
    svc = NotificationSendService(test_db)

    req = NotificationPreviewRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
    )
    result = svc.preview(req, triggered_by=actor_user.id)

    assert result.can_send is False
    assert result.status == "blocked"


def test_idempotency_returns_cached_result(test_db, client_factory, actor_user):
    cr_id = client_factory(email="idem@test.com").id
    svc = NotificationSendService(test_db)
    req = NotificationSendRequest(
        client_record_id=cr_id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "נושא", "body": "גוף"},
    )

    first = svc.send(
        req,
        triggered_by=actor_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000206",
    )
    second = svc.send(
        req,
        triggered_by=actor_user.id,
        idempotency_key="00000000-0000-4000-8000-000000000206",
    )

    assert first.notification_id == second.notification_id
