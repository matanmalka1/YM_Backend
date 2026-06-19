import json
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
from tests.helpers.identity import seed_client_identity

_seq = count(1)


def _create_report(db, user):
    idx = next(_seq)
    client = seed_client_identity(db, full_name=f"Audit Report {idx}", id_number=f"ARG{idx:06d}")
    return AnnualReportService(db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=user.id,
        created_by_name=user.full_name,
        deadline_type="custom",
    )


def _entry(db, report_id, action):
    return db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report_id)
        .filter(EntityAuditLog.action == action)
    ).one()


def test_detail_update_writes_generic_audit(test_db, test_user):
    report = _create_report(test_db, test_user)

    AnnualReportDetailService(test_db).update_detail(
        report.id,
        actor_id=test_user.id,
        donation_amount=250,
        internal_notes="בדיקה",
    )

    entry = _entry(test_db, report.id, ACTION_ANNUAL_REPORT_DETAIL_UPDATED)
    assert json.loads(entry.old_value) == {
        "donation_amount": None,
        "internal_notes": None,
    }
    assert json.loads(entry.new_value) == {
        "donation_amount": 250,
        "internal_notes": "בדיקה",
    }


def test_detail_update_skips_audit_when_values_do_not_change(test_db, test_user):
    report = _create_report(test_db, test_user)
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


def test_deadline_update_writes_generic_audit(test_db, test_user):
    report = _create_report(test_db, test_user)

    AnnualReportService(test_db).update_deadline(
        report.id,
        "standard",
        test_user.id,
        test_user.full_name,
    )

    entry = _entry(test_db, report.id, ACTION_ANNUAL_REPORT_DEADLINE_UPDATED)
    assert json.loads(entry.old_value) == {
        "deadline_type": "custom",
        "filing_deadline": None,
        "custom_deadline_note": None,
    }
    assert json.loads(entry.new_value)["deadline_type"] == "standard"


def test_annex_add_update_delete_write_generic_audit(test_db, test_user):
    report = _create_report(test_db, test_user)
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

    added = json.loads(_entry(test_db, report.id, ACTION_ANNEX_LINE_ADDED).new_value)
    updated = _entry(test_db, report.id, ACTION_ANNEX_LINE_UPDATED)
    deleted = json.loads(_entry(test_db, report.id, ACTION_ANNEX_LINE_DELETED).old_value)
    assert added == {
        "schedule": "schedule_b",
        "line_id": line.id,
        "line_number": 1,
        "data": {"rental_income": 12000.0},
        "notes": "ראשון",
    }
    assert json.loads(updated.old_value)["notes"] == "ראשון"
    assert json.loads(updated.new_value)["data"] == {"rental_income": 15000.0}
    assert deleted["notes"] == "עודכן"
