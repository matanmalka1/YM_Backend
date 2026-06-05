import pytest

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.repositories.annual_report_repository import AnnualReportRepository
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.exceptions import AppError, NotFoundError
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from tests.helpers.identity import seed_client_identity


def _create_report(db, *, full_name="AR Status Additional", id_number="ARSTAT001"):
    crm_client = seed_client_identity(db, full_name=full_name, id_number=id_number)
    report = AnnualReportService(db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
        notes=None,
    )
    return crm_client, report


def _move_to_in_preparation(service, report_id):
    service.transition_status(report_id, "collecting_docs", 1, "A")
    service.transition_status(report_id, "in_preparation", 1, "A")


def test_transition_rejects_unknown_status(test_db):
    _client, report = _create_report(test_db)

    with pytest.raises(AppError) as exc:
        AnnualReportService(test_db).transition_status(report.id, "not-a-status", 1, "A")
    assert exc.value.code == "ANNUAL_REPORT.INVALID_STATUS"


def test_pending_client_creates_real_client_scoped_signature_request(test_db):
    crm_client, report = _create_report(
        test_db,
        full_name="Pending Signature Person",
        id_number="ARSTAT002",
    )
    service = AnnualReportService(test_db)
    _move_to_in_preparation(service, report.id)

    result = service.transition_status(report.id, "pending_client", 1, "A")

    pending = SignatureRequestRepository(test_db).list_pending_by_annual_report(report.id)
    assert result.status == AnnualReportStatus.PENDING_CLIENT.value
    assert len(pending) == 1
    assert pending[0].client_record_id == crm_client.id
    assert pending[0].business_id is None
    assert pending[0].signer_name == "Pending Signature Person"


def test_pending_client_blocks_when_client_record_missing(test_db, monkeypatch):
    from app.clients.repositories.client_record_repository import ClientRecordRepository

    _client, report = _create_report(test_db, id_number="ARSTAT003")
    service = AnnualReportService(test_db)
    _move_to_in_preparation(service, report.id)
    monkeypatch.setattr(ClientRecordRepository, "get_by_id", lambda self, _id: None)

    with pytest.raises(NotFoundError) as exc:
        service.transition_status(report.id, "pending_client", 1, "A")

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"
    assert AnnualReportRepository(test_db).get_by_id(report.id).status == AnnualReportStatus.IN_PREPARATION


def test_update_deadline_invalid_and_custom_paths(test_db):
    _client, report = _create_report(test_db, id_number="ARSTAT004")
    service = AnnualReportService(test_db)

    with pytest.raises(AppError) as exc:
        service.update_deadline(report.id, "bad", 1, "A")
    assert exc.value.code == "ANNUAL_REPORT.INVALID_TYPE"

    updated = service.update_deadline(
        report.id,
        "custom",
        1,
        "A",
        custom_deadline_note="manual date handled externally",
    )
    assert updated.deadline_type == "custom"
    assert service.update_deadline(report.id, "standard", 1, "A").deadline_type == "standard"


def test_transition_closed_sets_financial_fields(test_db):
    _client, report = _create_report(test_db, id_number="ARSTAT005")
    service = AnnualReportService(test_db)
    service.repo.update(report.id, status=AnnualReportStatus.SUBMITTED)

    updated = service.transition_status(
        report.id,
        "closed",
        1,
        "A",
        assessment_amount=111.0,
        refund_due=22.0,
        tax_due=33.0,
    )
    assert updated.status == AnnualReportStatus.CLOSED.value
    assert float(updated.assessment_amount) == 111.0
