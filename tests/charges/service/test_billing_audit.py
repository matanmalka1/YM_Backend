import json
from itertools import count

from sqlalchemy import select

from app.audit.constants import ACTION_CANCELED, ACTION_ISSUED, ACTION_PAID
from app.audit.models.entity_audit_log import EntityAuditLog
from app.businesses.models.business import BusinessStatus
from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.services.billing_service import BillingService
from tests.helpers.identity import seed_client_with_business

_seq = count(1)


def _business(test_db):
    idx = next(_seq)
    _client, business = seed_client_with_business(
        test_db,
        full_name=f"Billing Audit Client {idx}",
        id_number=f"BSA{idx:07d}",
    )
    business.status = BusinessStatus.ACTIVE
    test_db.commit()
    return business


def test_issue_charge_audit_preserves_issued_action(test_db, test_user):
    business = _business(test_db)
    service = BillingService(test_db)
    charge = _charge(service, business, test_user.id)

    service.issue_charge(charge.id, actor_id=test_user.id)

    entry = _audit_entry(test_db, charge.id, ACTION_ISSUED)
    assert json.loads(entry.old_value) == {"status": ChargeStatus.DRAFT.value}
    assert json.loads(entry.new_value) == {"status": ChargeStatus.ISSUED.value}
    assert entry.note is None


def test_paid_charge_audit_preserves_paid_action(test_db, test_user):
    business = _business(test_db)
    service = BillingService(test_db)
    charge = _charge(service, business, test_user.id)
    service.issue_charge(charge.id, actor_id=test_user.id)

    service.mark_charge_paid(charge.id, actor_id=test_user.id)

    entry = _audit_entry(test_db, charge.id, ACTION_PAID)
    assert json.loads(entry.old_value) == {"status": ChargeStatus.ISSUED.value}
    assert json.loads(entry.new_value) == {"status": ChargeStatus.PAID.value}
    assert entry.note is None


def test_cancel_charge_audit_preserves_canceled_action(test_db, test_user):
    business = _business(test_db)
    service = BillingService(test_db)
    charge = _charge(service, business, test_user.id)
    service.issue_charge(charge.id, actor_id=test_user.id)

    service.cancel_charge(charge.id, actor_id=test_user.id, reason="Duplicate")

    entry = _audit_entry(test_db, charge.id, ACTION_CANCELED)
    assert json.loads(entry.old_value) == {"status": ChargeStatus.ISSUED.value}
    assert json.loads(entry.new_value) == {"status": ChargeStatus.CANCELED.value}
    assert entry.note == "Duplicate"


def _charge(service, business, actor_id):
    return service.create_charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=50,
        charge_type=ChargeType.CONSULTATION_FEE,
        actor_id=actor_id,
    )


def _audit_entry(db, charge_id: int, action: str) -> EntityAuditLog:
    return db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == "charge")
        .filter(EntityAuditLog.entity_id == charge_id)
        .filter(EntityAuditLog.action == action)
    ).one()
