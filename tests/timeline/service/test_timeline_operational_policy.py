from datetime import UTC, date, datetime
from decimal import Decimal

from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.audit_constants import (
    ACTION_CREATED,
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_CLIENT,
    entity_action,
)
from app.audit.repositories.audit_entity_audit_log_repository import (
    EntityAuditLogRepository,
)
from app.charges.models.charge import ChargeStatus, ChargeType
from app.common.enums import ObligationType
from app.notifications.models.notification import NotificationChannel, NotificationTrigger
from app.reminders.models.reminder import (
    ReminderActionType,
    ReminderStatus,
)
from app.timeline.services.timeline_service import TimelineService


def _business(create_client_with_business):
    _, business = create_client_with_business(
        full_name="Timeline Policy",
        id_number="TP100",
        business_name="Timeline Policy Business",
        opened_at=date(2026, 1, 1),
    )
    return business


def _event_types(events):
    return [event["event_type"] for event in events]


def test_timeline_includes_client_record_changes_and_dedups_created(
    test_db, test_user, create_client_with_business
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    audit_repo = EntityAuditLogRepository(test_db)
    audit_repo.append(
        entity_type=ENTITY_CLIENT,
        entity_id=business.client_id,
        performed_by=test_user.id,
        action=entity_action(ENTITY_CLIENT, ACTION_CREATED),
        new_value='{"full_name": "Timeline Policy"}',
    )
    audit_repo.append(
        entity_type=ENTITY_CLIENT,
        entity_id=business.client_id,
        performed_by=test_user.id,
        action=entity_action(ENTITY_CLIENT, ACTION_UPDATED),
        old_value='{"full_name": "Old"}',
        new_value='{"full_name": "New"}',
    )
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    change_events = [e for e in events if e["event_type"] == "client_record_changed"]
    assert len(change_events) == 1  # 'created' is deduped against client_created
    metadata = change_events[0]["metadata"]
    assert metadata["change_action"] == entity_action(ENTITY_CLIENT, ACTION_UPDATED)
    assert metadata["performed_by_name"] == test_user.full_name
    # creation still surfaces once, via the synthetic client_created event
    assert _event_types(events).count("client_created") == 1


def test_timeline_includes_annual_report_audit_changes(
    test_db, test_user, create_client_with_business, tax_calendar_entry_factory
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    entry = tax_calendar_entry_factory(
        obligation_type=ObligationType.ANNUAL_REPORT,
        tax_year=2025,
    )
    report = AnnualReport(
        client_record_id=business.client_id,
        created_by=test_user.id,
        tax_year=2025,
        tax_calendar_entry_id=entry.id,
        client_type=ClientAnnualFilingType.INDIVIDUAL,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        status=AnnualReportStatus.COLLECTING_DOCS,
    )
    test_db.add(report)
    test_db.flush()
    audit_repo = EntityAuditLogRepository(test_db)
    audit_repo.append(
        entity_type=ENTITY_ANNUAL_REPORT,
        entity_id=report.id,
        performed_by=test_user.id,
        action=entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED),  # deduped
    )
    audit_repo.append(
        entity_type=ENTITY_ANNUAL_REPORT,
        entity_id=report.id,
        performed_by=test_user.id,
        action=entity_action(ENTITY_ANNUAL_REPORT, ACTION_UPDATED),
        old_value='{"total_income": 1}',
        new_value='{"total_income": 2}',
    )
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    change_events = [e for e in events if e["event_type"] == "annual_report_changed"]
    assert len(change_events) == 1  # status_changed deduped
    metadata = change_events[0]["metadata"]
    assert metadata["entity_type"] == ENTITY_ANNUAL_REPORT
    assert metadata["entity_id"] == report.id
    assert metadata["change_action"] == entity_action(ENTITY_ANNUAL_REPORT, ACTION_UPDATED)


def test_timeline_date_range_excludes_out_of_range_events(test_db, create_client_with_business):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)

    _, total_before_cutoff = service.get_client_timeline(
        business.client_id, page=1, page_size=50, date_to=date(2000, 1, 1)
    )
    _, total_after_cutoff = service.get_client_timeline(
        business.client_id, page=1, page_size=50, date_from=date(2999, 1, 1)
    )
    _, total_unfiltered = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert total_before_cutoff == 0
    assert total_after_cutoff == 0
    assert total_unfiltered > 0


def test_timeline_excludes_scheduler_reminder_with_source_reference(
    test_db, create_client_with_business, reminder_factory
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    reminder_factory(
        fire_at=datetime(2026, 1, 10, tzinfo=UTC),
        action_type=ReminderActionType.SEND_NOTIFICATION,
        status=ReminderStatus.SCHEDULED,
        source_domain="client_record",
        source_id=business.client_id,
        commit=True,
    )

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "client_created" in _event_types(events)
    assert "reminder_created" not in _event_types(events)
    assert all(event.get("metadata", {}).get("source_domain") is None for event in events)


def test_timeline_excludes_noisy_notification_events(
    test_db, create_client_with_business, notification_factory
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    notification_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="Ready",
    )
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "client_created" in _event_types(events)
    assert "client_info_updated" not in _event_types(events)
    assert "notification_sent" not in _event_types(events)


def test_timeline_annual_report_status_events_use_entity_audit_source(
    test_db, test_user, create_client_with_business, tax_calendar_entry_factory
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    entry = tax_calendar_entry_factory(
        obligation_type=ObligationType.ANNUAL_REPORT,
        tax_year=2025,
    )
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
    audit = EntityAuditLogRepository(test_db).append(
        entity_type=ENTITY_ANNUAL_REPORT,
        entity_id=report.id,
        performed_by=test_user.id,
        action=entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED),
        old_value={"status": AnnualReportStatus.NOT_STARTED.value},
        new_value={"status": AnnualReportStatus.COLLECTING_DOCS.value},
        note="Started collection",
        actor_display_name=test_user.full_name,
        metadata_json={"client_record_id": business.client_id, "tax_year": 2025},
    )
    audit.performed_at = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)
    event = next(e for e in events if e["event_type"] == "annual_report_status_changed")

    assert event["timestamp"] == audit.performed_at
    assert event["timestamp"] != report.updated_at
    assert event["metadata"] == {
        "history_id": audit.id,
        "annual_report_id": report.id,
        "tax_year": 2025,
        "form_type": "1301",
        "from_status": "not_started",
        "to_status": "collecting_docs",
        "note": "Started collection",
    }


def test_timeline_keeps_charge_policy_events(test_db, create_client_with_business, charge_factory):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    charge_factory(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("250.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.PAID,
        created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        issued_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
        paid_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
    )
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "charge_created" in _event_types(events)
    assert "charge_issued" in _event_types(events)
    assert "charge_paid" in _event_types(events)
