from sqlalchemy.orm import Session

from app.audit.constants import (
    ACTION_CANCELED,
    ACTION_ISSUED,
    ACTION_PAID,
    ENTITY_CHARGE,
)
from app.audit.services.entity_audit_writer import EntityAuditWriter
from app.businesses.services.business_guards import (
    assert_business_belongs_to_legal_entity,
    validate_business_for_create,
)
from app.charges.models.charge import Charge, ChargeStatus
from app.charges.repositories.charge_repository import ChargeRepository
from app.charges.services.billing_audit import record_charge_status_audit
from app.charges.services.messages import (
    AMOUNT_MUST_BE_POSITIVE,
    CHARGE_ALREADY_CANCELED,
    CHARGE_CANNOT_CANCEL_PAID,
    CHARGE_DELETE_INVALID_STATUS,
    CHARGE_INVALID_STATUS_ISSUE,
    CHARGE_INVALID_STATUS_PAY,
    CHARGE_NOT_FOUND,
    CLIENT_NOT_FOUND,
)
from app.clients.guards.client_record_guards import assert_client_record_is_active
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.utils.time_utils import utcnow


class BillingService:
    def __init__(self, db: Session):
        self.db = db
        self.charge_repo = ChargeRepository(db)
        self._audit = EntityAuditWriter(db)

    def _validate_charge_scope(
        self,
        client_record_id: int,
        business_id: int | None,
        legal_entity_id: int | None = None,
    ) -> int | None:
        client_record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if not client_record:
            raise NotFoundError(
                CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                "CHARGE.CLIENT_NOT_FOUND",
            )
        if business_id is None:
            return None
        business = validate_business_for_create(self.db, business_id)
        assert_business_belongs_to_legal_entity(business, legal_entity_id)
        return business.id

    def create_charge(
        self,
        client_record_id: int,
        amount: float,
        charge_type: str,
        business_id: int | None = None,
        actor_id: int | None = None,
        period: str | None = None,
        months_covered: int = 1,
    ) -> Charge:
        if amount <= 0:
            raise AppError(AMOUNT_MUST_BE_POSITIVE, "CHARGE.AMOUNT_INVALID")
        client_record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if not client_record:
            raise NotFoundError(
                CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                "CHARGE.CLIENT_RECORD_NOT_FOUND",
            )
        assert_client_record_is_active(client_record)
        business_id = self._validate_charge_scope(
            client_record_id, business_id, client_record.legal_entity_id
        )
        charge = self.charge_repo.create(
            client_record_id=client_record.id,
            business_id=business_id,
            amount=amount,
            charge_type=charge_type,
            period=period,
            months_covered=months_covered,
            created_by=actor_id,
        )
        self._audit.record_create(
            ENTITY_CHARGE,
            charge.id,
            actor_id,
            new_value={
                "amount": str(amount),
                "charge_type": charge_type,
            },
        )
        return charge

    def issue_charge(self, charge_id: int, actor_id: int | None = None) -> Charge:
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(CHARGE_NOT_FOUND.format(charge_id=charge_id), "CHARGE.NOT_FOUND")
        if charge.status != ChargeStatus.DRAFT:
            raise AppError(
                CHARGE_INVALID_STATUS_ISSUE.format(status=charge.status.value),
                "CHARGE.INVALID_STATUS",
            )
        issued = self.charge_repo.update_status(
            charge_id,
            ChargeStatus.ISSUED,
            charge=charge,
            issued_at=utcnow(),
            issued_by=actor_id,
        )
        record_charge_status_audit(
            self._audit,
            charge_id,
            actor_id,
            ACTION_ISSUED,
            ChargeStatus.DRAFT,
            ChargeStatus.ISSUED,
        )
        return issued

    def mark_charge_paid(self, charge_id: int, actor_id: int | None = None) -> Charge:
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(CHARGE_NOT_FOUND.format(charge_id=charge_id), "CHARGE.NOT_FOUND")
        if charge.status != ChargeStatus.ISSUED:
            raise AppError(
                CHARGE_INVALID_STATUS_PAY.format(status=charge.status.value),
                "CHARGE.INVALID_STATUS",
            )
        paid = self.charge_repo.update_status(
            charge_id,
            ChargeStatus.PAID,
            charge=charge,
            paid_at=utcnow(),
            paid_by=actor_id,
        )
        record_charge_status_audit(
            self._audit,
            charge_id,
            actor_id,
            ACTION_PAID,
            ChargeStatus.ISSUED,
            ChargeStatus.PAID,
        )
        return paid

    def cancel_charge(
        self,
        charge_id: int,
        actor_id: int | None = None,
        reason: str | None = None,
    ) -> Charge:
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(CHARGE_NOT_FOUND.format(charge_id=charge_id), "CHARGE.NOT_FOUND")
        if charge.status == ChargeStatus.PAID:
            raise AppError(CHARGE_CANNOT_CANCEL_PAID, "CHARGE.INVALID_STATUS")
        if charge.status == ChargeStatus.CANCELED:
            raise ConflictError(CHARGE_ALREADY_CANCELED, "CHARGE.CONFLICT")
        old_status = charge.status.value
        canceled = self.charge_repo.update_status(
            charge_id,
            ChargeStatus.CANCELED,
            charge=charge,
            canceled_by=actor_id,
            canceled_at=utcnow(),
            cancellation_reason=reason,
        )
        record_charge_status_audit(
            self._audit,
            charge_id,
            actor_id,
            ACTION_CANCELED,
            old_status,
            ChargeStatus.CANCELED,
            note=reason,
        )
        return canceled

    def delete_charge(self, charge_id: int, actor_id: int | None = None) -> bool:
        charge = self.charge_repo.get_by_id(charge_id)
        if not charge:
            raise NotFoundError(CHARGE_NOT_FOUND.format(charge_id=charge_id), "CHARGE.NOT_FOUND")
        if charge.status not in (ChargeStatus.DRAFT, ChargeStatus.CANCELED):
            raise AppError(
                CHARGE_DELETE_INVALID_STATUS.format(status=charge.status.value),
                "CHARGE.INVALID_STATUS",
            )
        result = self.charge_repo.soft_delete(charge_id, deleted_by=actor_id)
        if result:
            self._audit.record_delete(ENTITY_CHARGE, charge_id, actor_id)
        return result

    def get_charge(self, charge_id: int) -> Charge:
        charge = self.charge_repo.get_by_id(charge_id)
        if not charge:
            raise NotFoundError(CHARGE_NOT_FOUND.format(charge_id=charge_id), "CHARGE.NOT_FOUND")
        return charge
