from datetime import date, timedelta

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
        full_name="Sig Repo List User",
        email="sig.repo.list@example.com",
        password="pass",
    )


def test_signature_request_repository_list_by_business_with_status(
    test_db, user_factory, create_client_with_business
):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    _client, business = create_client_with_business(
        full_name="Sig Repo List Client A",
        id_number="SIG-L-A",
        business_name="Sig Repo List Business A",
        opened_at=date(2026, 1, 1),
    )
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
