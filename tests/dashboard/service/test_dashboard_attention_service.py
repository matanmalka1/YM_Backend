"""Integration tests for DashboardAttentionService."""

from datetime import date, timedelta

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.dashboard.services.dashboard_attention_service import DashboardAttentionService
from app.work_queue.schemas.work_queue import WorkQueueUrgency
from tests.helpers.task_helpers import create_business


def test_attention_is_role_independent(test_db):
    """Attention has no role gate — build() surfaces items for advisor and secretary alike."""
    biz = create_business(test_db)
    test_db.add(
        Charge(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=500,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=31),
        )
    )
    test_db.commit()

    items = DashboardAttentionService(test_db).build()
    assert any(item["source_type"] == "charge" for item in items)


def test_unpaid_charge_appears_as_overdue(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.commit()

    items = DashboardAttentionService(test_db).build()
    charge_items = [i for i in items if i["source_type"] == "charge"]

    assert len(charge_items) == 1
    assert charge_items[0]["urgency"] == WorkQueueUrgency.OVERDUE
    assert charge_items[0]["amount"] == "500.00"
    assert "₪" not in charge_items[0]["amount"]
    assert charge_items[0]["href"] == f"/charges?charge_id={charge.id}"


def test_max_7_items_are_included(test_db):
    biz = create_business(test_db)
    for i in range(10):
        test_db.add(
            Charge(
                client_record_id=biz.client_id,
                business_id=biz.id,
                amount=100 + i,
                charge_type=ChargeType.OTHER,
                status=ChargeStatus.ISSUED,
                issued_at=date.today() - timedelta(days=31 + i),
            )
        )
    test_db.commit()

    items = DashboardAttentionService(test_db).build()
    assert len(items) <= 7
