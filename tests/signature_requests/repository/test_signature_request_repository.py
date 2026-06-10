from datetime import date, timedelta

from app.businesses.models.business import Business
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_with_business


def _user(test_db) -> User:
    user = User(
        full_name="Signature Repo User",
        email="signature.repo@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db, *, suffix: str) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name=f"Signature Repo Client {suffix}",
        id_number=f"SIG-R-{suffix}",
        business_name=f"Signature Repo Business {suffix}",
        opened_at=date(2026, 1, 1),
    )
    test_db.commit()
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
    req = repo.create_pending(
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
    return req


def test_signature_request_repository_pending_expired_and_audit_methods(test_db):
    repo = SignatureRequestRepository(test_db)
    user = _user(test_db)
    business_a = _business(test_db, suffix="A")
    business_b = _business(test_db, suffix="B")
    now = utcnow()
    canceled = _create(repo, business_a, user_id=user.id, title="Canceled")
    repo.update(canceled.id, status=SignatureRequestStatus.CANCELED)
    expired_pending = _create(repo, business_a, user_id=user.id, title="Expired Pending")
    active_pending = _create(repo, business_a, user_id=user.id, title="Active Pending")
    other_client_pending = _create(repo, business_b, user_id=user.id, title="Other Client")
    repo.update(
        expired_pending.id,
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token="tok-expired",
        sent_at=now - timedelta(days=2),
        expires_at=now - timedelta(minutes=1),
    )
    repo.update(
        active_pending.id,
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token="tok-active",
        sent_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
    )
    repo.update(
        other_client_pending.id,
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token="tok-other",
        sent_at=now - timedelta(days=3),
        expires_at=now + timedelta(days=1),
    )
    assert repo.get_by_token("tok-active").id == active_pending.id
    assert repo.count_by_business(business_a.id) == 3
    assert (
        repo.count_by_business(business_a.id, status=SignatureRequestStatus.PENDING_SIGNATURE) == 2
    )
    assert [item.id for item in repo.list_pending(page=1, page_size=10)] == [
        other_client_pending.id,
        expired_pending.id,
        active_pending.id,
    ]
    assert repo.count_pending() == 3
    assert (
        repo.get_pending_by_client_and_id_for_update(business_a.client_id, active_pending.id).id
        == active_pending.id
    )
    assert (
        repo.get_pending_by_client_and_id_for_update(business_b.client_id, active_pending.id)
        is None
    )
    assert repo.get_pending_by_client_and_id_for_update(business_a.client_id, canceled.id) is None
    assert [item.id for item in repo.list_expired_pending()] == [expired_pending.id]
    assert canceled.id not in [item.id for item in repo.list_expired_pending()]
    late = repo.append_audit_event(
        signature_request_id=active_pending.id, event_type="late", actor_type="system"
    )
    early = repo.append_audit_event(
        signature_request_id=active_pending.id, event_type="early", actor_type="system"
    )
    late.occurred_at = now + timedelta(minutes=1)
    early.occurred_at = now - timedelta(minutes=1)
    test_db.commit()
    assert [event.event_type for event in repo.list_audit_events(active_pending.id)] == [
        "early",
        "late",
    ]


def test_repository_update_missing_id_and_pending_by_annual_report(test_db):
    repo = SignatureRequestRepository(test_db)
    user = _user(test_db)
    business = _business(test_db, suffix="AR")
    assert repo.update(999999, status=SignatureRequestStatus.CANCELED) is None
    pending = _create(repo, business, user_id=user.id, title="Annual Pending", annual_report_id=77)
    canceled = _create(
        repo, business, user_id=user.id, title="Annual Canceled", annual_report_id=77
    )
    repo.update(canceled.id, status=SignatureRequestStatus.CANCELED)
    other = _create(repo, business, user_id=user.id, title="Different Report", annual_report_id=88)
    repo.update(pending.id, status=SignatureRequestStatus.PENDING_SIGNATURE)
    repo.update(other.id, status=SignatureRequestStatus.PENDING_SIGNATURE)
    assert [item.id for item in repo.list_pending_by_annual_report(77)] == [pending.id]
    assert canceled.id not in [item.id for item in repo.list_pending_by_annual_report(77)]
