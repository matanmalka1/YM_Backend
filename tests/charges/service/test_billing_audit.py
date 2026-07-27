from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_CHARGE_CANCELED,
    ACTION_CHARGE_ISSUED,
    ACTION_CHARGE_PAID,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.services.charge_billing_service import BillingService

_ACTOR_NAME = "Billing Actor"


def test_issue_charge_audit_preserves_issued_action(
    test_db, test_user, create_client_with_business
):
    _client, business = create_client_with_business()
    service = BillingService(test_db)
    charge = _charge(service, business, test_user.id)

    service.issue_charge(charge.id, actor_id=test_user.id, actor_name=_ACTOR_NAME)

    entry = _audit_entry(test_db, charge.id, ACTION_CHARGE_ISSUED)
    assert entry.old_value == {"status": ChargeStatus.DRAFT.value}
    assert entry.new_value == {"status": ChargeStatus.ISSUED.value}
    assert entry.note is None
    assert entry.metadata_json["client_record_id"] == business.client_id


def test_paid_charge_audit_preserves_paid_action(test_db, test_user, create_client_with_business):
    _client, business = create_client_with_business()
    service = BillingService(test_db)
    charge = _charge(service, business, test_user.id)
    service.issue_charge(charge.id, actor_id=test_user.id, actor_name=_ACTOR_NAME)

    service.mark_charge_paid(charge.id, actor_id=test_user.id, actor_name=_ACTOR_NAME)

    entry = _audit_entry(test_db, charge.id, ACTION_CHARGE_PAID)
    assert entry.old_value == {"status": ChargeStatus.ISSUED.value}
    assert entry.new_value == {"status": ChargeStatus.PAID.value}
    assert entry.note is None


def test_cancel_charge_audit_preserves_canceled_action(
    test_db, test_user, create_client_with_business
):
    _client, business = create_client_with_business()
    service = BillingService(test_db)
    charge = _charge(service, business, test_user.id)
    service.issue_charge(charge.id, actor_id=test_user.id, actor_name=_ACTOR_NAME)

    service.cancel_charge(
        charge.id, actor_id=test_user.id, reason="Duplicate", actor_name=_ACTOR_NAME
    )

    entry = _audit_entry(test_db, charge.id, ACTION_CHARGE_CANCELED)
    assert entry.old_value == {"status": ChargeStatus.ISSUED.value}
    assert entry.new_value == {"status": ChargeStatus.CANCELED.value}
    assert entry.note == "Duplicate"


def _charge(service, business, actor_id):
    return service.create_charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=50,
        charge_type=ChargeType.CONSULTATION_FEE,
        actor_id=actor_id,
        actor_name=_ACTOR_NAME,
    )


def _audit_entry(db, charge_id: int, action: str) -> EntityAuditLog:
    return db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == "charge")
        .filter(EntityAuditLog.entity_id == charge_id)
        .filter(EntityAuditLog.action == action)
    ).one()
