from datetime import date, datetime
from decimal import Decimal

from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository


def test_list_count_and_soft_delete(test_db, user_factory, create_client_with_business):
    repo = ChargeRepository(test_db)
    user = user_factory(
        full_name="Charge Admin",
        email="charge.admin@example.com",
        password="pass",
    )
    _client_a, business = create_client_with_business(full_name="Charge Client", id_number="CH001")
    _client_b, other_business = create_client_with_business(
        full_name="Other Client", id_number="CH002"
    )

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


def test_get_aging_buckets_includes_only_issued_and_not_deleted(
    test_db, create_client_with_business, actor_user
):
    repo = ChargeRepository(test_db)
    _client, business = create_client_with_business(full_name="Aging Client", id_number="CH003")

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
    repo.soft_delete(old.id, deleted_by=actor_user.id)

    rows, total = repo.get_aging_buckets_paginated(
        as_of_date=date(2026, 3, 22),
        page=1,
        page_size=10,
    )
    assert total == 1
    assert len(rows) == 1

    row = rows[0]
    assert row["client_record_id"] == business.client_id
    assert float(row["current"]) == 100.0
    assert float(row["days_30"]) == 0.0
    assert float(row["days_60"]) == 0.0
    assert float(row["days_90_plus"]) == 0.0
    assert float(row["total"]) == 100.0
    assert row["oldest_issued_at"].date().isoformat() == "2026-03-10"

    assert repo.get_by_id(draft.id) is not None
