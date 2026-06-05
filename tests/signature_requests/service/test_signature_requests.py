from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.businesses.models.business import Business
from app.core.exceptions import AppError, NotFoundError
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.signature_requests.services import create_request as create_request_module
from app.signature_requests.services import signature_request_validations as validations
from app.signature_requests.services.admin_actions import expire_overdue_requests
from app.signature_requests.services.signature_request_service import (
    SignatureRequestService,
)
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_with_business


def _business(db, suffix: str = "A") -> Business:
    _client, business = seed_client_with_business(
        db,
        full_name=f"Signature Service Client {suffix}",
        id_number=f"99999999{suffix}",
        business_name=f"Signature Service Business {suffix}",
        email="svc@example.com",
        opened_at=date(2026, 1, 1),
    )
    db.commit()
    return business


def _create(
    repo: SignatureRequestRepository,
    business: Business,
    *,
    user_id: int,
    title: str,
    annual_report_id: int | None = None,
):
    now = utcnow()
    return repo.create_pending(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=user_id,
        request_type=SignatureRequestType.CUSTOM
        if annual_report_id is None
        else SignatureRequestType.ANNUAL_REPORT_APPROVAL,
        title=title,
        signer_name="Signer",
        annual_report_id=annual_report_id,
        signing_token=f"token-{business.id}-{title}",
        sent_at=now,
        expires_at=now + timedelta(days=14),
        expiry_days=14,
    )


def test_expire_overdue_requests_marks_expired_and_audits(test_db, test_user):
    business = _business(test_db, "1")
    repo = SignatureRequestRepository(test_db)
    req = _create(repo, business, user_id=test_user.id, title="Expired")
    repo.update(
        req.id,
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token="expired-token",
        sent_at=utcnow() - timedelta(days=10),
        expires_at=utcnow() - timedelta(days=1),
    )
    assert expire_overdue_requests(repo) == 1
    assert repo.get_by_id(req.id).status == SignatureRequestStatus.EXPIRED
    assert any(e.event_type == "expired" for e in repo.list_audit_events(req.id))


def test_record_view_on_expired_request_sets_status_and_raises(test_db, test_user):
    business = _business(test_db, "2")
    repo = SignatureRequestRepository(test_db)
    req = _create(repo, business, user_id=test_user.id, title="Expired View")
    repo.update(
        req.id,
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token="view-token",
        sent_at=utcnow() - timedelta(days=5),
        expires_at=utcnow() - timedelta(days=1),
    )
    with pytest.raises(AppError) as exc_info:
        SignatureRequestService(test_db).record_view(token="view-token")
    assert exc_info.value.code == "SIGNATURE_REQUEST.EXPIRED"
    assert repo.get_by_id(req.id).status == SignatureRequestStatus.EXPIRED


def test_list_client_requests_invalid_status_raises_app_error(test_db):
    business = _business(test_db, "3")
    with pytest.raises(AppError) as exc_info:
        SignatureRequestService(test_db).list_client_requests(
            client_record_id=business.client_id,
            status="not_a_status",
        )
    assert exc_info.value.code == "SIGNATURE_REQUEST.INVALID_STATUS"


def test_service_get_by_token_returns_request(test_db, test_user):
    business = _business(test_db, "4")
    repo = SignatureRequestRepository(test_db)
    req = _create(repo, business, user_id=test_user.id, title="Token Lookup")
    repo.update(req.id, signing_token="lookup-token")
    assert SignatureRequestService(test_db).get_by_token("lookup-token").id == req.id


def test_create_request_sets_pending_token_and_expiry(test_db, test_user):
    business = _business(test_db, "create")

    req = SignatureRequestService(test_db).create_request(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=test_user.id,
        created_by_name=test_user.full_name,
        sent_by=test_user.id,
        sent_by_name=test_user.full_name,
        expiry_days=14,
        request_type=SignatureRequestType.CUSTOM.value,
        title="Create pending",
        signer_name="Signer",
    )

    assert req.status == SignatureRequestStatus.PENDING_SIGNATURE
    assert req.signing_token
    assert req.sent_at is not None
    assert req.expires_at is not None
    assert req.expiry_days == 14
    assert [
        event.event_type for event in SignatureRequestRepository(test_db).list_audit_events(req.id)
    ] == [
        "created",
        "sent",
    ]


def test_create_pending_requires_signing_link_fields(test_db, test_user):
    business = _business(test_db, "repo-invariant")

    with pytest.raises(ValueError):
        SignatureRequestRepository(test_db).create_pending(
            client_record_id=business.client_id,
            business_id=business.id,
            created_by=test_user.id,
            request_type=SignatureRequestType.CUSTOM,
            title="Broken pending",
            signer_name="Signer",
            signing_token="",
            sent_at=None,
            expires_at=None,
            expiry_days=14,
        )


def test_create_request_raises_when_business_missing():
    repo = SimpleNamespace(
        create_pending=lambda **kwargs: None,
        append_audit_event=lambda **kwargs: None,
        db=SimpleNamespace(),
    )
    business_repo = SimpleNamespace(get_by_id=lambda _business_id: None)
    client_record_repo = SimpleNamespace(
        get_by_id=lambda _client_record_id: SimpleNamespace(id=123, legal_entity_id=1)
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.signature_requests.services.create_request.ClientRecordRepository",
            lambda _db: client_record_repo,
        )
        with pytest.raises(NotFoundError) as exc_info:
            create_request_module.create_request(
                repo,
                business_repo,
                client_record_id=123,
                business_id=123,
                created_by=1,
                created_by_name="Advisor",
                sent_by=1,
                sent_by_name="Advisor",
                expiry_days=14,
                request_type="custom",
                title="Missing business",
                signer_name="Signer",
            )
    assert exc_info.value.code == "BUSINESS.NOT_FOUND"


def test_create_request_raises_on_invalid_type():
    client_record_repo = SimpleNamespace(
        get_by_id=lambda _client_record_id: SimpleNamespace(id=1, legal_entity_id=1)
    )
    repo = SimpleNamespace(
        create_pending=lambda **kwargs: None,
        append_audit_event=lambda **kwargs: None,
        db=object(),
    )
    business_repo = SimpleNamespace(
        get_by_id=lambda _business_id: SimpleNamespace(
            legal_entity_id=1, contact_email=None, contact_phone=None
        )
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.signature_requests.services.create_request.ClientRecordRepository",
            lambda _db: client_record_repo,
        )
        mp.setattr(
            "app.signature_requests.services.create_request.BusinessContactService",
            lambda _db: SimpleNamespace(
                contact_email=lambda _business: None,
                contact_phone=lambda _business: None,
            ),
        )
        with pytest.raises(AppError) as exc_info:
            create_request_module.create_request(
                repo,
                business_repo,
                client_record_id=1,
                business_id=1,
                created_by=1,
                created_by_name="Advisor",
                sent_by=1,
                sent_by_name="Advisor",
                expiry_days=14,
                request_type="not-a-valid-type",
                title="Bad type",
                signer_name="Signer",
            )
    assert exc_info.value.code == "SIGNATURE_REQUEST.INVALID_TYPE"


def test_create_request_falls_back_to_business_contact_details():
    captured = {}
    client_record_repo = SimpleNamespace(
        get_by_id=lambda _client_record_id: SimpleNamespace(id=7, legal_entity_id=9)
    )

    def _create(**kwargs):
        captured["create"] = kwargs
        return SimpleNamespace(id=42)

    repo = SimpleNamespace(
        create_pending=_create,
        append_audit_event=lambda **kwargs: captured.setdefault("audit", kwargs),
        db=object(),
    )
    business_repo = SimpleNamespace(
        get_by_id=lambda _business_id: SimpleNamespace(
            id=1,
            legal_entity_id=9,
            contact_email="biz@example.com",
            contact_phone="050-1111111",
        )
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.signature_requests.services.create_request.ClientRecordRepository",
            lambda _db: client_record_repo,
        )
        mp.setattr(
            "app.signature_requests.services.create_request.BusinessContactService",
            lambda _db: SimpleNamespace(
                contact_email=lambda _business: "biz@example.com",
                contact_phone=lambda _business: "050-1111111",
            ),
        )
        create_request_module.create_request(
            repo,
            business_repo,
            client_record_id=5,
            business_id=1,
            created_by=9,
            created_by_name="Advisor",
            sent_by=9,
            sent_by_name="Advisor",
            expiry_days=14,
            request_type="custom",
            title="Fallback contact",
            signer_name="Signer",
            signer_email=None,
            signer_phone=None,
        )
    assert captured["create"]["signer_email"] == "biz@example.com"
    assert captured["create"]["signer_phone"] == "050-1111111"
    assert captured["audit"]["event_type"] == "created"


def test_cancel_request_requires_pending_request_in_client_scope(test_db, test_user):
    business = _business(test_db, "6")
    repo = SignatureRequestRepository(test_db)
    req = _create(repo, business, user_id=test_user.id, title="Already signed")
    repo.update(req.id, status=SignatureRequestStatus.SIGNED)
    with pytest.raises(NotFoundError) as exc_info:
        SignatureRequestService(test_db).cancel_request(
            client_record_id=business.client_id,
            request_id=req.id,
            canceled_by=test_user.id,
            canceled_by_name=test_user.full_name,
            reason="Cancel after sign",
        )
    assert exc_info.value.code == "SIGNATURE_REQUEST.NOT_FOUND"


def test_get_or_raise_and_assert_signable_validation_branches(test_db, test_user):
    business = _business(test_db, "7")
    repo = SignatureRequestRepository(test_db)
    req = _create(repo, business, user_id=test_user.id, title="Validation")
    with pytest.raises(NotFoundError) as not_found_exc:
        validations.get_or_raise(repo, 999999)
    assert not_found_exc.value.code == "SIGNATURE_REQUEST.NOT_FOUND"
    repo.update(req.id, status=SignatureRequestStatus.SIGNED)
    with pytest.raises(AppError) as invalid_status_exc:
        validations.assert_pending(req)
    assert invalid_status_exc.value.code == "SIGNATURE_REQUEST.INVALID_STATUS"
