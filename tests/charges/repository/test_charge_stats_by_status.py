from datetime import date, datetime
from decimal import Decimal

from app.businesses.models.business import BusinessStatus
from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from tests.helpers.identity import seed_client_with_business


def _biz(test_db, name: str, id_number: str):
    _client, business = seed_client_with_business(
        test_db,
        full_name=name,
        id_number=id_number,
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def test_stats_by_status_respects_business_id_filter(test_db):
    repo = ChargeRepository(test_db)
    biz_a = _biz(test_db, "Stats BizA", "SB001")
    biz_b = _biz(test_db, "Stats BizB", "SB002")

    paid_a = repo.create(
        client_record_id=biz_a.client_id,
        business_id=biz_a.id,
        amount=Decimal("100.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
    )
    repo.update_status(paid_a.id, ChargeStatus.PAID)

    paid_b = repo.create(
        client_record_id=biz_b.client_id,
        business_id=biz_b.id,
        amount=Decimal("900.00"),
        charge_type=ChargeType.CONSULTATION_FEE,
    )
    repo.update_status(paid_b.id, ChargeStatus.PAID)

    stats = repo.stats_by_status(business_id=biz_a.id)

    assert stats["paid"]["count"] == 1
    assert Decimal(stats["paid"]["amount"]) == Decimal("100.00")
    assert "paid" not in stats or stats.get("paid", {}).get("count") != 2


def test_stats_by_status_respects_period_filter(test_db):
    repo = ChargeRepository(test_db)
    biz = _biz(test_db, "Stats Period", "SP001")

    mar = repo.create(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=Decimal("200.00"),
        charge_type=ChargeType.MONTHLY_RETAINER,
        period="2026-03",
    )
    repo.update_status(mar.id, ChargeStatus.PAID)

    apr = repo.create(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=Decimal("300.00"),
        charge_type=ChargeType.MONTHLY_RETAINER,
        period="2026-04",
    )
    repo.update_status(apr.id, ChargeStatus.PAID)

    stats = repo.stats_by_status(period="2026-03")

    assert stats["paid"]["count"] == 1
    assert Decimal(stats["paid"]["amount"]) == Decimal("200.00")


def test_stats_by_status_respects_issued_after_filter(test_db):
    repo = ChargeRepository(test_db)
    biz = _biz(test_db, "Stats IssuedAfter", "SI001")

    old = repo.create(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=Decimal("50.00"),
        charge_type=ChargeType.OTHER,
    )
    repo.update_status(old.id, ChargeStatus.ISSUED, issued_at=datetime(2025, 1, 15))

    recent = repo.create(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=Decimal("150.00"),
        charge_type=ChargeType.OTHER,
    )
    repo.update_status(recent.id, ChargeStatus.ISSUED, issued_at=datetime(2026, 3, 1))

    stats = repo.stats_by_status(issued_after=date(2026, 1, 1))

    assert stats["issued"]["count"] == 1
    assert Decimal(stats["issued"]["amount"]) == Decimal("150.00")
