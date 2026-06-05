from datetime import date, datetime
from decimal import Decimal

from app.businesses.models.business import BusinessStatus
from app.charge.models.charge import ChargeStatus, ChargeType
from app.charge.repositories.charge_repository import ChargeRepository
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from tests.helpers.identity import seed_client_with_business


def _user(test_db):
    user = User(
        full_name="Charge Admin",
        email="charge.admin@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db, name: str, id_number: str):
    _client, business = seed_client_with_business(
        test_db,
        full_name=name,
        id_number=id_number,
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def test_list_count_and_soft_delete(test_db):
    repo = ChargeRepository(test_db)
    user = _user(test_db)
    business = _business(test_db, "Charge Client", "CH001")
    other_business = _business(test_db, "Other Client", "CH002")

    draft = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("100.00"),
        charge_type=ChargeType.MONTHLY_RETAINER,
        created_by=user.id,
    )
    paid = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("200.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
        created_by=user.id,
    )
    repo.update_status(paid.id, ChargeStatus.PAID)

    other = repo.create(
        client_record_id=other_business.client_id,
        business_id=other_business.id,
        amount=Decimal("50.00"),
        charge_type=ChargeType.MONTHLY_RETAINER,
        created_by=user.id,
    )
    repo.update_status(other.id, ChargeStatus.ISSUED)

    assert repo.count_charges(client_record_id=business.client_id) == 2
    assert repo.count_charges(status=ChargeStatus.PAID) == 1

    business_charges = repo.list_charges(client_record_id=business.client_id)
    assert {c.id for c in business_charges} == {draft.id, paid.id}

    paid_list = repo.list_charges(status=ChargeStatus.PAID)
    assert [c.id for c in paid_list] == [paid.id]
    type_filtered = repo.list_charges(charge_type=ChargeType.CONSULTATION_FEE)
    assert [c.id for c in type_filtered] == [paid.id]
    assert repo.count_charges(charge_type=ChargeType.CONSULTATION_FEE) == 1

    deleted = repo.soft_delete(draft.id, deleted_by=user.id)
    assert deleted is True
    assert {c.id for c in repo.list_charges(client_record_id=business.client_id)} == {paid.id}
    assert repo.count_charges(client_record_id=business.client_id) == 1
    assert repo.soft_delete(999999, deleted_by=user.id) is False


def test_get_aging_buckets_includes_only_issued_and_not_deleted(test_db):
    repo = ChargeRepository(test_db)
    business = _business(test_db, "Aging Client", "CH003")

    current = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("100.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
    )
    old = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("250.00"),
        charge_type=ChargeType.MONTHLY_RETAINER,
    )
    draft = repo.create(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=Decimal("999.00"),
        charge_type=ChargeType.OTHER,
    )

    repo.update_status(current.id, ChargeStatus.ISSUED, issued_at=datetime(2026, 3, 10))
    repo.update_status(old.id, ChargeStatus.ISSUED, issued_at=datetime(2025, 12, 1))
    repo.soft_delete(old.id, deleted_by=1)

    rows = repo.get_aging_buckets(as_of_date=date(2026, 3, 22))
    assert len(rows) == 1

    row = rows[0]
    assert row.client_record_id == business.client_id
    assert float(row.current) == 100.0
    assert float(row.days_30) == 0.0
    assert float(row.days_60) == 0.0
    assert float(row.days_90_plus) == 0.0
    assert float(row.total) == 100.0
    assert row.oldest_issued_at.date().isoformat() == "2026-03-10"

    assert repo.get_by_id(draft.id) is not None
