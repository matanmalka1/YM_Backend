"""Tests: mark_ready_for_handover returns tuple, notification wiring, bulk, idempotency."""

from datetime import date

from app.binders.models.binder import Binder, BinderLocationStatus
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.binders.services.binder_service import BinderService
from app.notifications.models.notification import NotificationStatus
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import NotificationResult
from tests.helpers.identity import seed_client_identity


def _receive(
    db, client_id: int, user_id: int, period_month: int = 1, open_new: bool = False
) -> Binder:
    binder, _, _ = BinderService(db).receive_binder(
        client_record_id=client_id,
        received_at=date(2026, 1, 1),
        received_by=user_id,
        open_new_binder=open_new,
        materials=[
            {
                "material_type": "other",
                "period_year": 2026,
                "period_month_start": period_month,
                "period_month_end": period_month,
            }
        ],
    )
    return binder


def test_mark_ready_for_handover_returns_tuple(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Tuple Client", id_number="NB-100")
    binder = _receive(test_db, client.id, test_user.id)
    service = BinderLifecycleService(test_db)

    result = service.mark_ready_for_handover(binder.id, changed_by_user_id=test_user.id)

    assert isinstance(result, tuple)
    binder_out, notification = result
    assert binder_out.location_status == BinderLocationStatus.READY_FOR_HANDOVER
    assert isinstance(notification, NotificationResult)
    assert notification.status in ("sent", "skipped", "failed", "blocked")


def test_mark_ready_for_handover_auto_send_called_with_correct_params(
    test_db, test_user, monkeypatch
):
    """auto_send receives expected trigger, binder_id, client_record_id, idempotency_key."""
    client = seed_client_identity(test_db, full_name="AutoSend Client", id_number="NB-AUTOSEND")
    binder = _receive(test_db, client.id, test_user.id)

    service = BinderLifecycleService(test_db)
    auto_send_calls: list = []

    def fake_auto_send(**kwargs):
        auto_send_calls.append(kwargs)
        return NotificationResult(status="skipped", reason="test")

    monkeypatch.setattr(service.auto_send_service, "auto_send", fake_auto_send)

    binder_out, notif = service.mark_ready_for_handover(binder.id, changed_by_user_id=test_user.id)

    assert len(auto_send_calls) == 1
    call = auto_send_calls[0]
    assert call["trigger"].value == "binder_ready_for_handover"
    assert call["client_record_id"] == client.id
    assert call["binder_id"] == binder.id
    assert call["entity_id"] == binder.id
    assert "binder_ready_" in call["idempotency_key"]
    assert notif.status == "skipped"


def test_mark_ready_for_handover_skipped_when_no_email(test_db, test_user):
    """Client exists but has no email → notification status skipped, record saved."""
    client = seed_client_identity(
        test_db,
        full_name="No Email Client",
        id_number="NB-NOEMAIL",
        email=None,
    )
    binder = _receive(test_db, client.id, test_user.id)
    service = BinderLifecycleService(test_db)

    _, notification = service.mark_ready_for_handover(binder.id, changed_by_user_id=test_user.id)

    assert notification.status == "skipped"
    assert notification.notification_id is not None

    repo = NotificationRepository(test_db)
    record = repo.get_by_id(notification.notification_id)
    assert record is not None
    assert record.status == NotificationStatus.SKIPPED
    assert record.recipient is None


def test_mark_ready_for_handover_bulk_collects_results(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Bulk Client", id_number="NB-BULK-10")

    b1 = _receive(test_db, client.id, test_user.id, period_month=1)
    b2 = _receive(test_db, client.id, test_user.id, period_month=6, open_new=True)

    service = BinderLifecycleService(test_db)
    results = service.mark_ready_for_handover_bulk(
        client_record_id=client.id,
        until_period_year=2026,
        until_period_month=3,
        changed_by_user_id=test_user.id,
    )

    # Only b1 (period month 1 ≤ cutoff 3) should be returned
    assert len(results) == 1
    binder_out, notification = results[0]
    assert binder_out.id == b1.id
    assert isinstance(notification, NotificationResult)
    assert b2.id not in [r[0].id for r in results]


def test_auto_send_idempotency_same_key_returns_same_record(
    test_db, test_user, monkeypatch, binder_factory
):
    """Two auto_send calls with identical key produce one DB record, same notification_id."""

    from app.notifications.models.notification import NotificationTrigger
    from app.notifications.services.notification_auto_send_service import (
        NotificationAutoSendService,
    )
    from app.notifications.services.notification_policy_service import PolicyResult

    client = seed_client_identity(
        test_db, full_name="Idem Client", id_number="NB-IDEM-DIRECT", email=None
    )
    binder = binder_factory(client=client, actor=test_user)
    idempotency_key = f"test_idem_{client.id}"

    svc = NotificationAutoSendService(test_db)
    monkeypatch.setattr(svc.policy, "can_send", lambda *_a, **_kw: PolicyResult(blocked=False))
    # Stub renderer so context resolver doesn't need a real binder in DB
    monkeypatch.setattr(svc.renderer, "render", lambda *_a, **_kw: ("body", "subject"))
    monkeypatch.setattr(svc.resolver, "resolve", lambda **_kw: {})

    r1 = svc.auto_send(
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        client_record_id=client.id,
        idempotency_key=idempotency_key,
        binder_id=binder.id,
        entity_id=binder.id,
        entity_type="binder",
    )
    r2 = svc.auto_send(
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        client_record_id=client.id,
        idempotency_key=idempotency_key,
        binder_id=binder.id,
        entity_id=binder.id,
        entity_type="binder",
    )

    assert r1.notification_id is not None
    assert r1.notification_id == r2.notification_id

    repo = NotificationRepository(test_db)
    all_records = repo.list_paginated(client_record_id=client.id)
    assert all_records[1] == 1  # exactly one record created


def test_auto_send_idempotency_different_entity_id_returns_cached_record(
    test_db, test_user, monkeypatch, binder_factory
):
    """Same key but different entity_id: hash mismatch is logged, cached record still returned."""
    from app.notifications.models.notification import NotificationTrigger
    from app.notifications.services.notification_auto_send_service import (
        NotificationAutoSendService,
    )
    from app.notifications.services.notification_policy_service import PolicyResult

    client = seed_client_identity(
        test_db, full_name="Hash Mismatch Client", id_number="NB-HASH-MISMATCH", email=None
    )
    first_binder = binder_factory(client=client, actor=test_user)
    second_binder = binder_factory(client=client, actor=test_user)
    key = f"test_hash_mismatch_{client.id}"

    svc = NotificationAutoSendService(test_db)
    monkeypatch.setattr(svc.policy, "can_send", lambda *_a, **_kw: PolicyResult(blocked=False))
    monkeypatch.setattr(svc.renderer, "render", lambda *_a, **_kw: ("body", "subject"))
    monkeypatch.setattr(svc.resolver, "resolve", lambda **_kw: {})

    r1 = svc.auto_send(
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        client_record_id=client.id,
        idempotency_key=key,
        binder_id=first_binder.id,
        entity_id=first_binder.id,
        entity_type="binder",
    )
    r2 = svc.auto_send(
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        client_record_id=client.id,
        idempotency_key=key,
        binder_id=second_binder.id,
        entity_id=second_binder.id,
        entity_type="binder",
    )

    assert r1.notification_id is not None
    # Idempotency key match returns the original record despite different entity_id
    assert r2.notification_id == r1.notification_id
