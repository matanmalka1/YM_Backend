from datetime import date, datetime
from types import SimpleNamespace

from app.charges.models.charge import ChargeStatus, ChargeType
from app.timeline.timeline_binder_event_builders import (
    binder_handed_over_event,
    binder_lifecycle_change_event,
    binder_received_event,
)
from app.timeline.timeline_charge_event_builders import (
    charge_created_event,
    charge_paid_event,
    invoice_attached_event,
)


def test_binder_lifecycle_change_event_for_new_binder():
    binder = SimpleNamespace(id=11, binder_number="B-123")
    lifecycle_log = SimpleNamespace(
        field_name="location_status",
        old_value="null",
        new_value="in_office",
        changed_at=datetime(2026, 3, 1, 10, 0),
    )

    event = binder_lifecycle_change_event(binder, lifecycle_log)

    assert event["event_type"] == "binder_lifecycle_change"
    assert event["timestamp"] == datetime(2026, 3, 1, 10, 0)
    assert event["description"] == "קלסר B-123 הגיע למשרד"
    assert event["metadata"] == {
        "field_name": "location_status",
        "old_value": "null",
        "new_value": "in_office",
    }
    assert "actions" not in event
    assert "available_actions" not in event


def test_binder_lifecycle_change_event_for_regular_transition():
    binder = SimpleNamespace(id=12, binder_number="B-124")
    lifecycle_log = SimpleNamespace(
        field_name="location_status",
        old_value="in_office",
        new_value="ready_for_handover",
        changed_at=datetime(2026, 3, 2, 11, 0),
    )

    event = binder_lifecycle_change_event(binder, lifecycle_log)

    assert event["description"] == "קלסר B-124: במשרד ← מוכן למסירה"
    assert event["metadata"] == {
        "field_name": "location_status",
        "old_value": "in_office",
        "new_value": "ready_for_handover",
    }
    assert "actions" not in event
    assert "available_actions" not in event


def test_binder_received_event_includes_metadata_without_actions():
    binder = SimpleNamespace(id=9, binder_number="C-777", received_at=date(2026, 2, 15))

    event = binder_received_event(binder)

    assert event["event_type"] == "binder_received"
    assert event["timestamp"] == datetime(2026, 2, 15)
    assert event["metadata"] == {"binder_number": "C-777"}
    assert "actions" not in event
    assert "available_actions" not in event


def test_binder_handed_over_event_includes_recipient_metadata():
    binder = SimpleNamespace(
        id=10,
        binder_number="D-404",
        handed_over_at=date(2026, 3, 3),
        handover_recipient_name="Dana",
    )

    event = binder_handed_over_event(binder)

    assert event["event_type"] == "binder_handed_over"
    assert event["timestamp"] == datetime(2026, 3, 3)
    assert event["metadata"] == {
        "binder_number": "D-404",
        "handover_recipient_name": "Dana",
    }
    assert "actions" not in event
    assert "available_actions" not in event


def test_charge_created_event_includes_actions_and_metadata():
    charge = SimpleNamespace(
        id=5,
        charge_type=ChargeType.MONTHLY_RETAINER,
        status=ChargeStatus.DRAFT,
        amount=12.5,
        created_at=datetime(2026, 3, 2, 9, 30),
    )

    event = charge_created_event(charge)

    assert event["event_type"] == "charge_created"
    assert event["timestamp"] == datetime(2026, 3, 2, 9, 30)
    assert event["description"] == "חיוב חדש: ריטיינר חודשי"
    assert event["metadata"] == {"amount": 12.5, "status": "draft"}


def test_charge_paid_event_is_actionless_and_formats_amount():
    charge = SimpleNamespace(
        id=6,
        charge_type=ChargeType.MONTHLY_RETAINER,
        status=ChargeStatus.PAID,
        amount=200.75,
        paid_at=datetime(2026, 3, 4, 15, 45),
    )

    event = charge_paid_event(charge)

    assert event["event_type"] == "charge_paid"
    assert event["timestamp"] == datetime(2026, 3, 4, 15, 45)
    assert event["description"] == "חיוב שולם: ריטיינר חודשי"
    assert event["metadata"] == {"amount": 200.75}


def test_invoice_attached_event_includes_provider_metadata():
    charge = SimpleNamespace(id=7)
    invoice = SimpleNamespace(
        created_at=datetime(2026, 3, 5, 8, 0),
        provider="Stripe",
        external_invoice_id="INV-1001",
    )

    event = invoice_attached_event(charge, invoice)

    assert event["event_type"] == "invoice_attached"
    assert event["timestamp"] == datetime(2026, 3, 5, 8, 0)
    assert event["description"] == "חשבונית צורפה: INV-1001"
    assert event["metadata"] == {
        "provider": "Stripe",
        "external_invoice_id": "INV-1001",
    }
