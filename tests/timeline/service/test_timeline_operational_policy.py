from datetime import UTC, date, datetime
from decimal import Decimal

from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.models.annual_report_status_history import (
    AnnualReportStatusHistory,
)
from app.charge.models.charge import Charge, ChargeStatus, ChargeType
from app.notifications.models.notification import (
    Notification,
    NotificationChannel,
    NotificationTrigger,
)
from app.reminders.models.reminder import (
    Reminder,
    ReminderActionType,
    ReminderStatus,
)
from app.timeline.services.timeline_service import TimelineService
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_tax_calendar_entry_for_annual


def _business(test_db):
    client = seed_client_identity(test_db, full_name="Timeline Policy", id_number="TP100")
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Timeline Policy Business",
        opened_at=date(2026, 1, 1),
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_id = client.id
    return business


def _event_types(events):
    return [event["event_type"] for event in events]


def test_timeline_excludes_scheduler_reminder_with_source_reference(test_db):
    service = TimelineService(test_db)
    business = _business(test_db)
    reminder = Reminder(
        fire_at=datetime(2026, 1, 10, tzinfo=UTC),
        action_type=ReminderActionType.SEND_NOTIFICATION,
        status=ReminderStatus.SCHEDULED,
        source_domain="client_record",
        source_id=business.client_id,
    )
    test_db.add(reminder)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "client_created" in _event_types(events)
    assert "reminder_created" not in _event_types(events)
    assert all(event.get("metadata", {}).get("source_domain") is None for event in events)


def test_timeline_excludes_noisy_notification_events(test_db):
    service = TimelineService(test_db)
    business = _business(test_db)
    notification = Notification(
        client_record_id=business.client_id,
        business_id=business.id,
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="Ready",
    )
    test_db.add(notification)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "client_created" in _event_types(events)
    assert "client_info_updated" not in _event_types(events)
    assert "notification_sent" not in _event_types(events)


def test_timeline_annual_report_status_events_use_history_source(test_db, test_user):
    service = TimelineService(test_db)
    business = _business(test_db)
    entry = create_tax_calendar_entry_for_annual(test_db, 2025)
    report = AnnualReport(
        client_record_id=business.client_id,
        created_by=test_user.id,
        tax_year=2025,
        tax_calendar_entry_id=entry.id,
        client_type=ClientAnnualFilingType.INDIVIDUAL,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        status=AnnualReportStatus.COLLECTING_DOCS,
        updated_at=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
    )
    test_db.add(report)
    test_db.flush()
    history = AnnualReportStatusHistory(
        annual_report_id=report.id,
        from_status=AnnualReportStatus.NOT_STARTED,
        to_status=AnnualReportStatus.COLLECTING_DOCS,
        changed_by=test_user.id,
        note="Started collection",
        occurred_at=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
    )
    test_db.add(history)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)
    event = next(e for e in events if e["event_type"] == "annual_report_status_changed")

    assert event["timestamp"] == history.occurred_at
    assert event["timestamp"] != report.updated_at
    assert event["metadata"] == {
        "history_id": history.id,
        "annual_report_id": report.id,
        "tax_year": 2025,
        "form_type": "1301",
        "from_status": "not_started",
        "to_status": "collecting_docs",
        "note": "Started collection",
    }


def test_timeline_keeps_charge_policy_events(test_db):
    service = TimelineService(test_db)
    business = _business(test_db)
    charge = Charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("250.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.PAID,
        created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        issued_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
        paid_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
    )
    test_db.add(charge)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "charge_created" in _event_types(events)
    assert "charge_issued" in _event_types(events)
    assert "charge_paid" in _event_types(events)
