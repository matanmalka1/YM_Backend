from datetime import datetime
from types import SimpleNamespace

import pytest

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.core.exceptions import AppError
from tests.helpers.identity import seed_client_identity


def _create_report(db):
    crm_client = seed_client_identity(db, full_name="AR Status Additional", id_number="ARSTAT001")
    report = AnnualReportService(db).create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
        notes=None,
    )
    return report


def test_transition_submitted_requires_readiness(test_db, monkeypatch):
    report = _create_report(test_db)
    svc = AnnualReportService(test_db)

    # move to pending_client so submitted transition is valid
    class _SigSvc:
        def __init__(self, db):
            self.db = db

        def create_request(self, **kwargs):
            return SimpleNamespace(id=1)

        def cancel_request(self, **kwargs):
            return None

    class _SigRepo:
        def __init__(self, db):
            self.db = db

        def list_pending_by_annual_report(self, report_id):
            return []

    import app.signature_requests.repositories.signature_request_repository as sig_repo_mod
    import app.signature_requests.services.signature_request_service as sig_service_mod

    monkeypatch.setattr(sig_service_mod, "SignatureRequestService", _SigSvc)
    monkeypatch.setattr(sig_repo_mod, "SignatureRequestRepository", _SigRepo)

    svc.transition_status(report.id, "collecting_docs", 1, "A")
    svc.transition_status(report.id, "in_preparation", 1, "A")
    svc.transition_status(report.id, "pending_client", 1, "A")

    class _ReadinessSvc:
        def __init__(self, db):
            self.db = db

        def get_readiness_check(self, report_id):
            return SimpleNamespace(is_ready=False, issues=["missing docs", "no totals"])

    import app.annual_reports.services.readiness_service as readiness_mod

    monkeypatch.setattr(readiness_mod, "AnnualReportReadinessService", _ReadinessSvc)

    with pytest.raises(AppError) as exc:
        svc.transition_status(report.id, "submitted", 1, "A")

    assert exc.value.code == "ANNUAL_REPORT.INVALID_STATUS"


def test_pending_client_transition_calls_signature_hooks(test_db, monkeypatch):
    report = _create_report(test_db)
    svc = AnnualReportService(test_db)

    svc.transition_status(report.id, "collecting_docs", 1, "A")

    called = {"created": 0, "canceled": 0}

    class _SigSvc:
        def __init__(self, db):
            self.db = db

        def create_request(self, **kwargs):
            called["created"] += 1
            return SimpleNamespace(id=1)

        def cancel_request(self, **kwargs):
            called["canceled"] += 1

    class _SigRepo:
        def __init__(self, db):
            self.db = db

        def list_pending_by_annual_report(self, report_id):
            return [SimpleNamespace(id=10)]

    import app.signature_requests.repositories.signature_request_repository as sig_repo_mod
    import app.signature_requests.services.signature_request_service as sig_service_mod

    monkeypatch.setattr(sig_service_mod, "SignatureRequestService", _SigSvc)
    monkeypatch.setattr(sig_repo_mod, "SignatureRequestRepository", _SigRepo)

    svc.transition_status(report.id, "in_preparation", 1, "A")
    result = svc.transition_status(report.id, "pending_client", 1, "A")

    assert result.status == AnnualReportStatus.PENDING_CLIENT.value
    assert called["created"] == 1
    assert called["canceled"] >= 1


def test_transition_rejects_unknown_status(test_db):
    report = _create_report(test_db)
    svc = AnnualReportService(test_db)

    with pytest.raises(AppError) as exc:
        svc.transition_status(report.id, "not-a-status", 1, "A")
    assert exc.value.code == "ANNUAL_REPORT.INVALID_STATUS"


def test_transition_from_pending_client_cancels_requests(test_db, monkeypatch):
    report = _create_report(test_db)
    svc = AnnualReportService(test_db)

    class _SigSvc:
        def __init__(self, db):
            self.db = db

        def create_request(self, **kwargs):
            return SimpleNamespace(id=1)

        def cancel_request(self, **kwargs):
            return None

    class _SigRepo:
        def __init__(self, db):
            self.db = db

        def list_pending_by_annual_report(self, report_id):
            return [SimpleNamespace(id=9)]

    import app.annual_reports.services.readiness_service as readiness_mod
    import app.signature_requests.repositories.signature_request_repository as sig_repo_mod
    import app.signature_requests.services.signature_request_service as sig_service_mod

    monkeypatch.setattr(sig_service_mod, "SignatureRequestService", _SigSvc)
    monkeypatch.setattr(sig_repo_mod, "SignatureRequestRepository", _SigRepo)
    monkeypatch.setattr(
        readiness_mod,
        "AnnualReportReadinessService",
        lambda db: SimpleNamespace(
            get_readiness_check=lambda _rid: SimpleNamespace(is_ready=True, issues=[]),
        ),
    )

    svc.transition_status(report.id, "collecting_docs", 1, "A")
    svc.transition_status(report.id, "in_preparation", 1, "A")
    svc.transition_status(report.id, "pending_client", 1, "A")
    submitted_at = datetime(2026, 1, 10, 12, 0, 0)
    moved = svc.transition_status(
        report.id,
        "submitted",
        1,
        "A",
        submitted_at=submitted_at,
        ita_reference="ITA-123",
    )
    assert moved.status == AnnualReportStatus.SUBMITTED.value
    assert moved.ita_reference == "ITA-123"


def test_update_deadline_invalid_and_custom_paths(test_db):
    report = _create_report(test_db)
    svc = AnnualReportService(test_db)

    with pytest.raises(AppError) as exc:
        svc.update_deadline(report.id, "bad", 1, "A")
    assert exc.value.code == "ANNUAL_REPORT.INVALID_TYPE"

    updated = svc.update_deadline(
        report.id,
        "custom",
        1,
        "A",
        custom_deadline_note="manual date handled externally",
    )
    assert updated.deadline_type == "custom"

    std = svc.update_deadline(report.id, "standard", 1, "A")
    assert std.deadline_type == "standard"


def test_transition_closed_sets_financial_fields(test_db):
    report = _create_report(test_db)
    svc = AnnualReportService(test_db)
    svc.repo.update(report.id, status=AnnualReportStatus.SUBMITTED)

    updated = svc.transition_status(
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


def _patch_sig_service(monkeypatch) -> dict:
    """Patch signature service + repo; return captured kwargs dict from create_request."""
    import app.signature_requests.repositories.signature_request_repository as sig_repo_mod
    import app.signature_requests.services.signature_request_service as sig_service_mod

    captured: dict = {}

    class _SigSvc:
        def __init__(self, db):
            self.db = db

        def create_request(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id=99)

        def cancel_request(self, **kwargs):
            pass

    class _SigRepo:
        def __init__(self, db):
            self.db = db

        def list_pending_by_annual_report(self, report_id):
            return []

    monkeypatch.setattr(sig_service_mod, "SignatureRequestService", _SigSvc)
    monkeypatch.setattr(sig_repo_mod, "SignatureRequestRepository", _SigRepo)
    return captured


def _report_at_in_preparation(db, full_name: str, id_number: str):
    crm_client = seed_client_identity(db=db, full_name=full_name, id_number=id_number)
    svc = AnnualReportService(db)
    report = svc.create_report(
        client_record_id=crm_client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
        notes=None,
    )
    svc.transition_status(report.id, "collecting_docs", 1, "A")
    svc.transition_status(report.id, "in_preparation", 1, "A")
    return crm_client, report, svc


def test_pending_client_creates_signature_without_business(test_db, monkeypatch):
    """pending_client transition succeeds and creates signature even when no Business exists."""
    crm_client, report, svc = _report_at_in_preparation(test_db, "No Business Client", "NOBIZ001")
    captured = _patch_sig_service(monkeypatch)

    result = svc.transition_status(report.id, "pending_client", 1, "A")

    assert result.status == AnnualReportStatus.PENDING_CLIENT.value
    assert captured.get("business_id") is None
    assert captured.get("signer_name") == "No Business Client"
    assert captured.get("client_record_id") == crm_client.id


def test_pending_client_signer_name_from_person(test_db, monkeypatch):
    """signer_name resolves from Person.full_name, not LegalEntity.official_name."""
    _crm_client, report, svc = _report_at_in_preparation(test_db, "Person Name", "PRSN001")
    captured = _patch_sig_service(monkeypatch)

    svc.transition_status(report.id, "pending_client", 1, "A")

    assert captured.get("signer_name") == "Person Name"


def test_pending_client_blocks_when_client_record_missing(test_db, monkeypatch):
    """Transition to pending_client raises CLIENT_RECORD.NOT_FOUND before status is committed."""
    from app.clients.repositories.client_record_repository import ClientRecordRepository
    from app.core.exceptions import NotFoundError

    _crm_client, report, svc = _report_at_in_preparation(test_db, "Ghost Client", "GHOST001")

    monkeypatch.setattr(ClientRecordRepository, "get_by_id", lambda self, _id: None)

    with pytest.raises(NotFoundError) as exc:
        svc.transition_status(report.id, "pending_client", 1, "A")

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"

    from app.annual_reports.models.annual_report_enums import AnnualReportStatus as S
    from app.annual_reports.repositories.annual_report_repository import AnnualReportRepository

    fresh = AnnualReportRepository(test_db).get_by_id(report.id)
    assert fresh.status == S.IN_PREPARATION


def test_pending_client_ignores_business_when_resolving_signer(test_db, monkeypatch):
    """business_id is always None and signer_name never comes from Business, even when one exists."""
    from datetime import date

    from app.businesses.models.business import Business, BusinessStatus

    crm_client, report, svc = _report_at_in_preparation(
        test_db, "Client With Business", "WITHBIZ001"
    )
    business = Business(
        legal_entity_id=crm_client.legal_entity_id,
        business_name="DIFFERENT BUSINESS NAME",
        status=BusinessStatus.ACTIVE,
        opened_at=date.today(),
    )
    test_db.add(business)
    test_db.flush()

    captured = _patch_sig_service(monkeypatch)

    svc.transition_status(report.id, "pending_client", 1, "A")

    assert captured.get("business_id") is None
    assert captured.get("signer_name") == "Client With Business"
    assert captured.get("signer_name") != "DIFFERENT BUSINESS NAME"
