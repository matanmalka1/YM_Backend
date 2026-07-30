from itertools import count

from sqlalchemy import select

from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.services.annual_report_detail_service import AnnualReportDetailService
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.audit.audit_constants import (
    ACTION_ANNEX_LINE_ADDED,
    ACTION_ANNEX_LINE_DELETED,
    ACTION_ANNEX_LINE_UPDATED,
    ACTION_ANNUAL_REPORT_DEADLINE_UPDATED,
    ACTION_ANNUAL_REPORT_DETAIL_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog

_seq = count(1)


def _entry(db, report_id, action):
    return db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report_id)
        .filter(EntityAuditLog.action == action)
    ).one()


def test_detail_update_writes_generic_audit(test_db, test_user, annual_report_service_factory):
    report = annual_report_service_factory(actor=test_user, deadline_type="custom")

    AnnualReportDetailService(test_db).update_detail(
        report.id,
        actor_id=test_user.id,
        donation_amount=250,
        internal_notes="בדיקה",
    )

    entry = _entry(test_db, report.id, ACTION_ANNUAL_REPORT_DETAIL_UPDATED)
    assert entry.old_value == {
        "donation_amount": None,
        "internal_notes": None,
    }
    assert entry.new_value == {
        "donation_amount": 250,
        "internal_notes": "בדיקה",
    }


def test_detail_update_skips_audit_when_values_do_not_change(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user, deadline_type="custom")
    service = AnnualReportDetailService(test_db)
    service.update_detail(report.id, actor_id=test_user.id, donation_amount=250)

    service.update_detail(report.id, actor_id=test_user.id, donation_amount=250)

    entries = test_db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report.id)
        .filter(EntityAuditLog.action == ACTION_ANNUAL_REPORT_DETAIL_UPDATED)
    ).all()
    assert len(entries) == 1


def test_deadline_update_writes_generic_audit(test_db, test_user, annual_report_service_factory):
    report = annual_report_service_factory(actor=test_user, deadline_type="custom")

    AnnualReportService(test_db).update_deadline(
        report.id,
        "standard",
        test_user.id,
        test_user.full_name,
    )

    entry = _entry(test_db, report.id, ACTION_ANNUAL_REPORT_DEADLINE_UPDATED)
    assert entry.old_value == {
        "deadline_type": "custom",
        "filing_deadline": None,
        "custom_deadline_note": None,
    }
    assert entry.new_value["deadline_type"] == "standard"


def test_annex_add_update_delete_write_generic_audit(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user, deadline_type="custom")
    service = AnnualReportService(test_db)
    schedule = AnnualReportSchedule.SCHEDULE_B

    line = service.add_annex_line(
        report.id,
        schedule,
        {"rental_income": 12000},
        "ראשון",
        actor_id=test_user.id,
    )
    service.update_annex_line(
        report.id,
        line.id,
        {"rental_income": 15000},
        "עודכן",
        actor_id=test_user.id,
    )
    service.delete_annex_line(report.id, line.id, actor_id=test_user.id)

    added = _entry(test_db, report.id, ACTION_ANNEX_LINE_ADDED).new_value
    updated = _entry(test_db, report.id, ACTION_ANNEX_LINE_UPDATED)
    deleted = _entry(test_db, report.id, ACTION_ANNEX_LINE_DELETED).old_value
    assert added == {
        "schedule": "schedule_b",
        "line_id": line.id,
        "line_number": 1,
        "data": {"rental_income": 12000.0},
        "notes": "ראשון",
    }
    assert updated.old_value["notes"] == "ראשון"
    assert updated.new_value["data"] == {"rental_income": 15000.0}
    assert deleted["notes"] == "עודכן"
