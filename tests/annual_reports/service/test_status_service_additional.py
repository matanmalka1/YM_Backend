import pytest
from sqlalchemy import select

from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.repositories.annual_report_repository import AnnualReportRepository
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.audit.audit_constants import ACTION_STATUS_CHANGED, ENTITY_ANNUAL_REPORT, entity_action
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import ObligationStatus
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
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


def test_pending_client_creates_real_client_scoped_signature_request(test_db, actor_user):
    crm_client, report = _create_report(
        test_db,
        actor_user.id,
        full_name="Pending Signature Person",
        id_number="ARSTAT002",
    )
    service = AnnualReportService(test_db)
    _move_to_in_preparation(service, report.id, actor_user.id)

    result = service.transition_status(
        report.id, "awaiting_verification", actor_user.id, actor_user.full_name
    )

    pending = SignatureRequestRepository(test_db).list_pending_by_annual_report(report.id)
    assert result.status == ObligationStatus.AWAITING_VERIFICATION.value
    assert len(pending) == 1
    assert pending[0].client_record_id == crm_client.id
    assert pending[0].business_id is None
    assert pending[0].signer_name == "Pending Signature Person"


def test_pending_client_blocks_when_client_record_missing(test_db, actor_user, monkeypatch):
    from app.clients.repositories.client_record_repository import ClientRecordRepository

    _client, report = _create_report(test_db, actor_user.id, id_number="ARSTAT003")
    service = AnnualReportService(test_db)
    _move_to_in_preparation(service, report.id, actor_user.id)
    monkeypatch.setattr(ClientRecordRepository, "get_by_id", lambda self, _id: None)

    with pytest.raises(NotFoundError) as exc:
        service.transition_status(report.id, "awaiting_verification", actor_user.id, actor_user.full_name)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"
    assert (
        AnnualReportRepository(test_db).get_by_id(report.id).status
        == ObligationStatus.IN_PROGRESS
    )


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


def test_transition_closed_sets_financial_fields(test_db, actor_user):
    _client, report = _create_report(test_db, actor_user.id, id_number="ARSTAT005")
    service = AnnualReportService(test_db)
    service.repo.update(report.id, status=ObligationStatus.SUBMITTED)

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
