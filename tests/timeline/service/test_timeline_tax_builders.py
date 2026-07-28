from datetime import datetime
from types import SimpleNamespace

from app.annual_reports.models.annual_report_enums import PrimaryAnnualReportForm
from app.common.enums import ObligationStatus
from app.timeline.timeline_tax_builders import (
    annual_report_status_changed_event,
)


def test_annual_report_status_changed_event_includes_form_and_status_hebrew():
    report = SimpleNamespace(
        id=3,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        tax_year=2024,
        status=ObligationStatus.AWAITING_INPUT,
        updated_at=datetime(2026, 1, 1, 12, 0),
    )
    history = SimpleNamespace(
        id=10,
        from_status=ObligationStatus.AWAITING_INPUT,
        to_status=ObligationStatus.INPUT_RECEIVED,
        note="מסמכים התקבלו",
        occurred_at=datetime(2026, 1, 2, 12, 0),
    )

    event = annual_report_status_changed_event(report, history)

    assert event["event_type"] == "annual_report_status_changed"
    assert event["timestamp"] == datetime(2026, 1, 2, 12, 0)
    assert event["description"] == "דוח שנתי 1301 (2024): ממתין לחומר ← החומר התקבל"
    assert event["metadata"] == {
        "history_id": 10,
        "annual_report_id": 3,
        "tax_year": 2024,
        "form_type": "1301",
        "from_status": "awaiting_input",
        "to_status": "input_received",
        "note": "מסמכים התקבלו",
    }
    assert "actions" not in event
    assert "available_actions" not in event
