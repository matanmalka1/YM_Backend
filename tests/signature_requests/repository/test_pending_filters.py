"""Filter coverage for the pending signature-requests queue."""

from datetime import date, timedelta

from app.signature_requests.models.signature_request import SignatureRequestType
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.users.models.user import User
from app.utils.time_utils import start_of_day, utcnow


def _user(user_factory) -> User:
    return user_factory(
        full_name="Pending Filter User",
        email="pending.filter@example.com",
        password="pass",
    )


def _business(create_client_with_business, suffix):
    _client, business = create_client_with_business(
        full_name=f"Pending Client {suffix}",
        id_number=f"SIG-P-{suffix}",
        business_name=f"Pending Business {suffix}",
        opened_at=date(2026, 1, 1),
    )
    return business


def _pending(
    repo,
    business,
    user_id,
    *,
    title,
    request_type=SignatureRequestType.CUSTOM,
    signer_email=None,
    created_on=None,
    expires_on=None,
):
    now = utcnow()
    req = repo.create_pending(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=user_id,
        request_type=request_type,
        title=title,
        signer_name="Signer",
        signer_email=signer_email,
        signing_token=f"tok-{business.id}-{title}",
        sent_at=now,
        expires_at=now + timedelta(days=14),
        expiry_days=14,
    )
    if created_on is not None:
        req.created_at = start_of_day(created_on)
    if expires_on is not None:
        req.expires_at = start_of_day(expires_on)
    repo.db.commit()
    repo.db.refresh(req)
    return req


def test_pending_filter_by_client_record_id(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz_a = _business(create_client_with_business, "001")
    biz_b = _business(create_client_with_business, "002")
    target = _pending(repo, biz_a, user.id, title="A")
    _pending(repo, biz_b, user.id, title="B")

    items = repo.list_pending(client_record_id=biz_a.client_id)
    total = repo.count_pending(client_record_id=biz_a.client_id)

    assert total == 1
    assert [r.id for r in items] == [target.id]


def test_pending_filter_by_request_type(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz = _business(create_client_with_business, "003")
    custom = _pending(repo, biz, user.id, title="C", request_type=SignatureRequestType.CUSTOM)
    _pending(
        repo,
        biz,
        user.id,
        title="P",
        request_type=SignatureRequestType.POWER_OF_ATTORNEY,
    )

    items = repo.list_pending(request_type=SignatureRequestType.CUSTOM)
    total = repo.count_pending(request_type=SignatureRequestType.CUSTOM)

    assert total == 1
    assert [r.id for r in items] == [custom.id]


def test_pending_filter_by_signer_email(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz = _business(create_client_with_business, "004")
    target = _pending(repo, biz, user.id, title="E1", signer_email="alice@example.com")
    _pending(repo, biz, user.id, title="E2", signer_email="bob@example.com")

    items = repo.list_pending(signer_email="alice")
    total = repo.count_pending(signer_email="alice")

    assert total == 1
    assert [r.id for r in items] == [target.id]


def test_pending_filter_by_expires_before(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz = _business(create_client_with_business, "005")
    soon = _pending(repo, biz, user.id, title="SOON", expires_on=date(2026, 2, 1))
    _pending(repo, biz, user.id, title="LATER", expires_on=date(2026, 5, 1))

    # expires_before=2026-02-01 → upper bound is start of next day, so SOON (midnight) is included.
    items = repo.list_pending(expires_before=date(2026, 2, 1))
    total = repo.count_pending(expires_before=date(2026, 2, 1))

    assert total == 1
    assert [r.id for r in items] == [soon.id]


def test_pending_filters_combined_with_and(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz_a = _business(create_client_with_business, "006")
    biz_b = _business(create_client_with_business, "007")
    match = _pending(repo, biz_a, user.id, title="M", request_type=SignatureRequestType.CUSTOM)
    # Same client, wrong type.
    _pending(repo, biz_a, user.id, title="WT", request_type=SignatureRequestType.POWER_OF_ATTORNEY)
    # Right type, wrong client.
    _pending(repo, biz_b, user.id, title="WC", request_type=SignatureRequestType.CUSTOM)

    items = repo.list_pending(
        client_record_id=biz_a.client_id, request_type=SignatureRequestType.CUSTOM
    )
    total = repo.count_pending(
        client_record_id=biz_a.client_id, request_type=SignatureRequestType.CUSTOM
    )

    assert total == 1
    assert [r.id for r in items] == [match.id]


def test_pending_no_match_returns_empty(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz = _business(create_client_with_business, "008")
    _pending(repo, biz, user.id, title="X")

    items = repo.list_pending(client_record_id=999999)
    total = repo.count_pending(client_record_id=999999)

    assert total == 0
    assert items == []


def test_pending_deterministic_tie_breaker(test_db, user_factory, create_client_with_business):
    repo = SignatureRequestRepository(test_db)
    user = _user(user_factory)
    biz = _business(create_client_with_business, "009")
    # Same sent_at → id asc tie-breaker decides order.
    same = utcnow()
    first = _pending(repo, biz, user.id, title="T1")
    second = _pending(repo, biz, user.id, title="T2")
    first.sent_at = same
    second.sent_at = same
    test_db.commit()

    items = repo.list_pending()

    assert [r.id for r in items] == [first.id, second.id]
