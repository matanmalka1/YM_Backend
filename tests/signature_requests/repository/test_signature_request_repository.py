from datetime import date, timedelta

from app.businesses.models.business import Business
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.users.models.user import User
from app.utils.time_utils import utcnow


def _user(user_factory) -> User:
    return user_factory(
        full_name="Signature Repo User",
        email="signature.repo@example.com",
        password="pass",
    )


def _business(create_client_with_business, *, suffix: str) -> Business:
    _client, business = create_client_with_business(
        full_name=f"Signature Repo Client {suffix}",
        id_number=f"SIG-R-{suffix}",
        business_name=f"Signature Repo Business {suffix}",
        opened_at=date(2026, 1, 1),
    )
    return business


def _create(
    repo: SignatureRequestRepository,
    business: Business,
    *,
    user_id: int,
    title: str,
):
    now = utcnow()
    req = repo.create_pending(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=user_id,
        request_type=SignatureRequestType.CUSTOM,
        title=title,
        signer_name="Signer",
        signing_token=f"token-{business.id}-{title}",
        sent_at=now,
        expires_at=now + timedelta(days=14),
        expiry_days=14,
    )
    return req


def test_signature_request_repository_pending_and_expired_queries(
    test_db, user_factory, create_client_with_business
):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    business_a = _business(create_client_with_business, suffix="A")
    business_b = _business(create_client_with_business, suffix="B")
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


def test_repository_update_missing_id_returns_none(test_db):
    repo = SignatureRequestRepository(test_db)
    assert repo.update(999999, status=SignatureRequestStatus.CANCELED) is None
