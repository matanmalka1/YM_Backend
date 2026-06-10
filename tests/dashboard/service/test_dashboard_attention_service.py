"""Integration tests for DashboardAttentionService."""

from datetime import date, timedelta

from app.charge.models.charge import Charge, ChargeStatus, ChargeType
from app.alerts.services.alert_service import DashboardAttentionService
from app.users.models.user import UserRole
from app.work_queue.schemas.work_queue import WorkQueueUrgency
from tests.helpers.task_helpers import create_business


def test_returns_empty_for_non_advisor(test_db):
    service = DashboardAttentionService(test_db)
    assert service.build(user_role=None) == []
    assert service.build(user_role=UserRole.SECRETARY) == []


def test_unpaid_charge_appears_as_overdue(test_db):
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

    items = DashboardAttentionService(test_db).build(user_role=UserRole.ADVISOR)
    charge_items = [i for i in items if i["source_type"] == "charge"]

    assert len(charge_items) == 1
    assert charge_items[0]["urgency"] == WorkQueueUrgency.OVERDUE
    assert charge_items[0]["amount"] is not None
    assert charge_items[0]["href"] == "/charges"


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

    items = DashboardAttentionService(test_db).build(user_role=UserRole.ADVISOR)
    assert len(items) <= 7
