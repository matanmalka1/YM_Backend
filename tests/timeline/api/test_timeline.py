from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import count

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.charge.models.charge import Charge, ChargeStatus, ChargeType
from app.invoice.models.invoice import Invoice
from app.notification.models.notification import (
    Notification,
    NotificationChannel,
    NotificationTrigger,
)
from app.reminders.models.reminder import (
    Reminder,
    ReminderActionType,
    ReminderStatus,
)
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from tests.helpers.identity import seed_business, seed_client_identity

_client_seq = count(1)


def _business(db):
    idx = next(_client_seq)
    crm_client = seed_client_identity(
        db,
        full_name=f"Timeline Client {idx}",
        id_number=f"2323232{idx:03d}",
    )
    business = seed_business(
        db,
        legal_entity_id=crm_client.legal_entity_id,
        business_name=f"Timeline Business {idx}",
        opened_at=date.today(),
    )
    db.commit()
    db.refresh(business)
    business.client_id = crm_client.id
    return business


def test_timeline_orders_events_newest_first(
    client, test_db, advisor_headers, test_user, monkeypatch
):
    business = _business(test_db)
    monkeypatch.setattr(
        "app.timeline.services.timeline_service.build_client_events",
        lambda *args, **kwargs: [],
    )

    binder = Binder(
        client_record_id=business.client_id,
        binder_number="B-100",
        period_start=date.today() - timedelta(days=5),
        handed_over_at=date.today() - timedelta(days=1),
        location_status=BinderLocationStatus.HANDED_OVER,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
    )
    test_db.add(binder)

    charge = Charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("500.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        created_at=datetime.now(UTC) - timedelta(days=4),
        issued_at=datetime.now(UTC) - timedelta(days=3),
    )
    test_db.add(charge)

    sig = SignatureRequest(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=test_user.id,
        request_type=SignatureRequestType.CUSTOM,
        title="Sign",
        signer_name="Signer",
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        created_at=datetime.now(UTC) - timedelta(days=6),
        sent_at=datetime.now(UTC) - timedelta(days=5),
    )
    test_db.add(sig)

    reminder = Reminder(
        fire_at=datetime.now(UTC) - timedelta(days=7),
        action_type=ReminderActionType.SEND_NOTIFICATION,
        status=ReminderStatus.SCHEDULED,
        source_domain="client_record",
        source_id=business.client_id,
        created_at=datetime.now(UTC) - timedelta(days=7),
    )
    test_db.add(reminder)

    notification = Notification(
        client_record_id=business.client_id,
        business_id=business.id,
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        channel=NotificationChannel.EMAIL,
        recipient="test@example.com",
        content_snapshot="Ready",
        created_at=datetime.now(UTC) - timedelta(days=8),
    )
    test_db.add(notification)

    test_db.flush()
    invoice = Invoice(
        charge_id=charge.id,
        provider="dummy",
        external_invoice_id="INV-1",
        issued_at=datetime.now(UTC) - timedelta(days=2),
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    test_db.add(invoice)
    test_db.commit()

    resp = client.get(
        f"/api/v1/clients/{business.client_id}/timeline?page=1&page_size=5",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 5
    events = data["events"]
    event_types = [event["event_type"] for event in events]
    assert "reminder_created" not in event_types
    timestamps = [datetime.fromisoformat(e["timestamp"]) for e in events]
    assert timestamps == sorted(timestamps, reverse=True)


def test_timeline_applies_bulk_limits(client, test_db, advisor_headers, monkeypatch):
    business = _business(test_db)
    monkeypatch.setattr(
        "app.timeline.services.timeline_service.build_client_events",
        lambda *args, **kwargs: [],
    )
    for _ in range(210):
        test_db.add(
            Charge(
                client_record_id=business.client_id,
                business_id=business.id,
                amount=Decimal("10.00"),
                charge_type=ChargeType.CONSULTATION_FEE,
                status=ChargeStatus.DRAFT,
                created_at=datetime.now(UTC),
            )
        )
    test_db.commit()

    resp = client.get(
        f"/api/v1/clients/{business.client_id}/timeline?page=1&page_size=200",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 210
    assert len(data["events"]) == 200
