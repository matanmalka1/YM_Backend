import pytest
from sqlalchemy import select

from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.audit.audit_constants import ACTION_STATUS_CHANGED, ENTITY_ANNUAL_REPORT, entity_action
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from tests.helpers.identity import seed_client_identity


def _create_report(db, actor_id: int, *, full_name="AR Status Additional", id_number="ARSTAT001"):
    crm_client = seed_client_identity(db, full_name=full_name, id_number=id_number)
    report = AnnualReportService(db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=actor_id,
        created_by_name="Tester",
        deadline_type="standard",
        notes=None,
    )
    return crm_client, report


def _move_to_in_preparation(service, report_id, actor_id: int):
    # One stage at a time. not_started and collecting_docs merged into
    # awaiting_input, so the ladder from the start is input_received then in_progress.
    service.transition_status(report_id, "input_received", actor_id, "A")
    service.transition_status(report_id, "in_progress", actor_id, "A")


def test_transition_rejects_unknown_status(test_db, actor_user):
    _client, report = _create_report(test_db, actor_user.id)

    with pytest.raises(AppError) as exc:
        AnnualReportService(test_db).transition_status(
            report.id, "not-a-status", actor_user.id, actor_user.full_name
        )
    assert exc.value.code == "ANNUAL_REPORT.INVALID_STATUS"


def test_update_deadline_invalid_and_custom_paths(test_db, actor_user):
    _client, report = _create_report(test_db, actor_user.id, id_number="ARSTAT004")
    service = AnnualReportService(test_db)

    with pytest.raises(AppError) as exc:
        service.update_deadline(report.id, "bad", actor_user.id, actor_user.full_name)
    assert exc.value.code == "ANNUAL_REPORT.INVALID_TYPE"

    updated = service.update_deadline(
        report.id,
        "custom",
        actor_user.id,
        actor_user.full_name,
        custom_deadline_note="manual date handled externally",
    )
    assert updated.deadline_type == "custom"
    assert (
        service.update_deadline(
            report.id, "standard", actor_user.id, actor_user.full_name
        ).deadline_type
        == "standard"
    )


def test_update_deadline_note_only_keeps_existing_type(test_db, actor_user):
    _client, report = _create_report(test_db, actor_user.id, id_number="ARSTAT004B")
    service = AnnualReportService(test_db)

    service.update_deadline(report.id, "extended", actor_user.id, actor_user.full_name)

    # Partial update: only custom_deadline_note is sent (deadline_type omitted).
    updated = service.update_deadline(
        report.id,
        None,
        actor_user.id,
        actor_user.full_name,
        custom_deadline_note="late filing agreed",
    )
    assert updated.deadline_type == "extended"
    assert updated.custom_deadline_note == "late filing agreed"


def test_submitting_records_the_financial_outcome(test_db, actor_user, monkeypatch):
    """`closed` merged into `submitted`, so one act records both.

    The assessment used to be recorded by a second transition that followed
    submission; there is no second transition now. Readiness is stubbed because
    this test is about what submitting *records*, not about what gates it — the
    gate has its own tests.
    """
    _client, report = _create_report(test_db, actor_user.id, id_number="ARSTAT005")
    service = AnnualReportService(test_db)
    service.repo.update(report.id, status=ObligationStatus.AWAITING_VERIFICATION)
    monkeypatch.setattr(
        "app.annual_reports.services.annual_report_status_service."
        "AnnualReportStatusService._assert_filing_readiness",
        lambda self, report_id: None,
    )

    updated = service.transition_status(
        report.id,
        "submitted",
        actor_user.id,
        actor_user.full_name,
        assessment_amount=111.0,
        refund_due=22.0,
        tax_due=33.0,
    )
    assert updated.status == ObligationStatus.SUBMITTED.value
    assert float(updated.assessment_amount) == 111.0


def test_status_audit_failure_rolls_back_status_mutation(test_db, actor_user, monkeypatch):
    _client, report = _create_report(test_db, actor_user.id, id_number="ARSTAT006")

    def fail_record_status_change(_self, *_args, **_kwargs):
        raise AppError("audit failed", ErrorCode.AUDIT_FORBIDDEN_FIELD)

    monkeypatch.setattr(EntityAuditWriter, "record_status_change", fail_record_status_change)

    with pytest.raises(AppError):
        with test_db.begin_nested():
            AnnualReportService(test_db).transition_status(
                report.id,
                "awaiting_input",
                actor_user.id,
                actor_user.full_name,
                note="must roll back",
            )

    test_db.expire_all()
    persisted = test_db.scalar(select(AnnualReport).where(AnnualReport.id == report.id))
    assert persisted.status == ObligationStatus.AWAITING_INPUT
    status_audit_count = test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT,
            EntityAuditLog.entity_id == report.id,
            EntityAuditLog.action == entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED),
        )
    ).all()
    assert status_audit_count == []
