from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.charges.models.charge import ChargeStatus, ChargeType
from app.invoices.models.invoice import Invoice
from app.notifications.models.notification import NotificationChannel, NotificationTrigger
from app.reminders.models.reminder import (
    Reminder,
    ReminderActionType,
    ReminderStatus,
)
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)


def test_timeline_orders_events_newest_first(
    client,
    test_db,
    advisor_headers,
    test_user,
    monkeypatch,
    create_client_with_business,
    binder_factory,
    charge_factory,
    signature_request_factory,
    notification_factory,
):
    _, business = create_client_with_business(full_name="Timeline Client")
    monkeypatch.setattr(
        "app.timeline.services.timeline_service.build_client_events",
        lambda *args, **kwargs: [],
    )

    binder_factory(
        client_record_id=business.client_id,
        binder_number="B-100",
        period_start=date.today() - timedelta(days=5),
        handed_over_at=date.today() - timedelta(days=1),
        location_status=BinderLocationStatus.HANDED_OVER,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
        commit=True,
    )

    charge = charge_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("500.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        created_at=datetime.now(UTC) - timedelta(days=4),
        issued_at=datetime.now(UTC) - timedelta(days=3),
    )

    signature_request_factory(
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

    reminder = Reminder(
        fire_at=datetime.now(UTC) - timedelta(days=7),
        action_type=ReminderActionType.SEND_NOTIFICATION,
        status=ReminderStatus.SCHEDULED,
        source_domain="client_record",
        source_id=business.client_id,
        created_at=datetime.now(UTC) - timedelta(days=7),
    )
    test_db.add(reminder)

    notification_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        channel=NotificationChannel.EMAIL,
        recipient="test@example.com",
        content_snapshot="Ready",
        created_at=datetime.now(UTC) - timedelta(days=8),
    )

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
        f"/api/v1/clients/{business.client_id}/timeline?page=1",
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


def test_timeline_applies_bulk_limits(
    client, test_db, advisor_headers, monkeypatch, create_client_with_business, charge_factory
):
    _, business = create_client_with_business(full_name="Timeline Client")
    monkeypatch.setattr(
        "app.timeline.services.timeline_service.build_client_events",
        lambda *args, **kwargs: [],
    )
    for _ in range(210):
        charge_factory(
            client_record_id=business.client_id,
            business_id=business.id,
            amount=Decimal("10.00"),
            charge_type=ChargeType.CONSULTATION_FEE,
            status=ChargeStatus.DRAFT,
        )
    test_db.commit()

    resp = client.get(
        f"/api/v1/clients/{business.client_id}/timeline?page=1",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 210
    assert len(data["events"]) == data["page_size"]
