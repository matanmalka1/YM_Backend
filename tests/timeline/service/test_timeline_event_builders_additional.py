from datetime import datetime
from types import SimpleNamespace

from app.charges.models.charge import ChargeStatus, ChargeType
from app.timeline.services.timeline_charge_event_builders import charge_issued_event


def test_charge_issued_event_is_information_only():
    charge = SimpleNamespace(
        id=91,
        issued_at=datetime(2026, 3, 9, 9, 15),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        amount=320.0,
    )

    event = charge_issued_event(charge)

    assert event["event_type"] == "charge_issued"
    assert event["timestamp"] == datetime(2026, 3, 9, 9, 15)
    assert event["metadata"] == {"amount": 320.0}
    assert "actions" not in event
    assert "available_actions" not in event
