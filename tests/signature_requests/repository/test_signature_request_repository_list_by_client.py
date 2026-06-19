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
from app.users.services.user_auth_service import AuthService
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_with_business


def _user(test_db) -> User:
    user = User(
        full_name="Sig Repo List User",
        email="sig.repo.list@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db, suffix: str) -> Business:
    _client, business = seed_client_with_business(
        test_db,
        full_name=f"Sig Repo List Client {suffix}",
        id_number=f"SIG-L-{suffix}",
        business_name=f"Sig Repo List Business {suffix}",
        opened_at=date(2026, 1, 1),
    )
    test_db.commit()
    return business


def test_signature_request_repository_list_by_business_with_status(test_db):
    repo = SignatureRequestRepository(test_db)
    user = _user(test_db)
    business = _business(test_db, "A")
    now = utcnow()
    canceled = repo.create_pending(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=user.id,
        request_type=SignatureRequestType.CUSTOM,
        title="Canceled",
        signer_name="Signer",
        signing_token="canceled-token",
        sent_at=now,
        expires_at=now + timedelta(days=14),
        expiry_days=14,
    )
    repo.update(canceled.id, status=SignatureRequestStatus.CANCELED)
    pending = repo.create_pending(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=user.id,
        request_type=SignatureRequestType.CUSTOM,
        title="Pending",
        signer_name="Signer",
        signing_token="pending-token",
        sent_at=now,
        expires_at=now + timedelta(days=14),
        expiry_days=14,
    )
    assert {r.id for r in repo.list_by_business(business.id, page=1, page_size=10)} == {
        canceled.id,
        pending.id,
    }
    pending_only = repo.list_by_business(
        business.id,
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        page=1,
        page_size=10,
    )
    assert [r.id for r in pending_only] == [pending.id]
