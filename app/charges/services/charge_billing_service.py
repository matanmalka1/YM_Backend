from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_CHARGE_CANCELED,
    ACTION_CHARGE_ISSUED,
    ACTION_CHARGE_PAID,
    ENTITY_CHARGE,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.businesses.business_guards import (
    assert_business_belongs_to_legal_entity,
    validate_business_for_create,
)
from app.charges.charge_billing_audit import record_charge_status_audit
from app.charges.charge_messages import (
    AMOUNT_MUST_BE_POSITIVE,
    CHARGE_ALREADY_CANCELED,
    CHARGE_CANNOT_CANCEL_PAID,
    CHARGE_DELETE_INVALID_STATUS,
    CHARGE_INVALID_STATUS_ISSUE,
    CHARGE_INVALID_STATUS_PAY,
    CHARGE_NOT_FOUND,
    CHARGE_UPDATE_INVALID_STATUS,
)
from app.charges.models.charge import Charge, ChargeStatus
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.guards.client_record_guards import assert_client_record_is_active
from app.clients.services.client_service import get_client_or_raise
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.utils.time_utils import utcnow


def _audit_value(value):
    """JSON-safe rendering for audit diffs (Decimal amounts, enum charge_type)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


def _charge_context(charge: Charge) -> dict:
    """metadata_json client context for a charge audit row (§8)."""
    meta: dict = {"client_record_id": charge.client_record_id}
    if charge.business_id is not None:
        meta["business_id"] = charge.business_id
    return meta


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
        get_client_or_raise(self.db, client_record_id)
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
        actor_name: str | None = None,
        period: str | None = None,
        months_covered: int = 1,
    ) -> Charge:
        if amount <= 0:
            raise AppError(AMOUNT_MUST_BE_POSITIVE, ErrorCode.CHARGE_AMOUNT_INVALID)
        client_record = get_client_or_raise(self.db, client_record_id)
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
            actor_display_name=actor_name,
            metadata_json=_charge_context(charge),
            new_value={
                "amount": str(amount),
                "charge_type": charge_type,
            },
        )
        return charge

    def update_charge(
        self,
        charge_id: int,
        patch: dict,
        actor_id: int | None = None,
        actor_name: str | None = None,
    ) -> Charge:
        """Apply a partial update to a draft charge.

        ``patch`` holds only the fields the client actually sent (exclude_unset),
        so an absent key leaves the column untouched.
        """
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(
                CHARGE_NOT_FOUND.format(charge_id=charge_id), ErrorCode.CHARGE_NOT_FOUND
            )
        if charge.status != ChargeStatus.DRAFT:
            raise AppError(
                CHARGE_UPDATE_INVALID_STATUS.format(status=charge.status.value),
                ErrorCode.CHARGE_INVALID_STATUS,
            )

        if "amount" in patch and patch["amount"] <= 0:
            raise AppError(AMOUNT_MUST_BE_POSITIVE, ErrorCode.CHARGE_AMOUNT_INVALID)
        if "business_id" in patch and patch["business_id"] is not None:
            client_record = get_client_or_raise(self.db, charge.client_record_id)
            self._validate_charge_scope(
                charge.client_record_id, patch["business_id"], client_record.legal_entity_id
            )

        changed = {key: value for key, value in patch.items() if getattr(charge, key) != value}
        if not changed:
            return charge

        old_value = {key: _audit_value(getattr(charge, key)) for key in changed}
        updated = self.charge_repo.update_fields(charge_id, charge=charge, **changed)
        self._audit.record_update(
            ENTITY_CHARGE,
            charge_id,
            actor_id,
            old_value=old_value,
            new_value={key: _audit_value(value) for key, value in changed.items()},
            actor_display_name=actor_name,
            metadata_json=_charge_context(charge),
        )
        return updated or charge

    def issue_charge(
        self, charge_id: int, actor_id: int | None = None, actor_name: str | None = None
    ) -> Charge:
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(
                CHARGE_NOT_FOUND.format(charge_id=charge_id), ErrorCode.CHARGE_NOT_FOUND
            )
        if charge.status != ChargeStatus.DRAFT:
            raise AppError(
                CHARGE_INVALID_STATUS_ISSUE.format(status=charge.status.value),
                ErrorCode.CHARGE_INVALID_STATUS,
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
            ACTION_CHARGE_ISSUED,
            ChargeStatus.DRAFT,
            ChargeStatus.ISSUED,
            actor_display_name=actor_name,
            metadata_json=_charge_context(charge),
        )
        return issued

    def mark_charge_paid(
        self, charge_id: int, actor_id: int | None = None, actor_name: str | None = None
    ) -> Charge:
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(
                CHARGE_NOT_FOUND.format(charge_id=charge_id), ErrorCode.CHARGE_NOT_FOUND
            )
        if charge.status != ChargeStatus.ISSUED:
            raise AppError(
                CHARGE_INVALID_STATUS_PAY.format(status=charge.status.value),
                ErrorCode.CHARGE_INVALID_STATUS,
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
            ACTION_CHARGE_PAID,
            ChargeStatus.ISSUED,
            ChargeStatus.PAID,
            actor_display_name=actor_name,
            metadata_json=_charge_context(charge),
        )
        return paid

    def cancel_charge(
        self,
        charge_id: int,
        actor_id: int | None = None,
        reason: str | None = None,
        actor_name: str | None = None,
    ) -> Charge:
        charge = self.charge_repo.get_by_id_for_update(charge_id)
        if not charge:
            raise NotFoundError(
                CHARGE_NOT_FOUND.format(charge_id=charge_id), ErrorCode.CHARGE_NOT_FOUND
            )
        if charge.status == ChargeStatus.PAID:
            raise AppError(CHARGE_CANNOT_CANCEL_PAID, ErrorCode.CHARGE_INVALID_STATUS)
        if charge.status == ChargeStatus.CANCELED:
            raise ConflictError(CHARGE_ALREADY_CANCELED, ErrorCode.CHARGE_CONFLICT)
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
            ACTION_CHARGE_CANCELED,
            old_status,
            ChargeStatus.CANCELED,
            note=reason,
            actor_display_name=actor_name,
            metadata_json=_charge_context(charge),
        )
        return canceled

    def delete_charge(
        self, charge_id: int, actor_id: int | None = None, actor_name: str | None = None
    ) -> bool:
        charge = self.charge_repo.get_by_id(charge_id)
        if not charge:
            raise NotFoundError(
                CHARGE_NOT_FOUND.format(charge_id=charge_id), ErrorCode.CHARGE_NOT_FOUND
            )
        if charge.status not in (ChargeStatus.DRAFT, ChargeStatus.CANCELED):
            raise AppError(
                CHARGE_DELETE_INVALID_STATUS.format(status=charge.status.value),
                ErrorCode.CHARGE_INVALID_STATUS,
            )
        metadata = _charge_context(charge)
        result = self.charge_repo.soft_delete(charge_id, deleted_by=actor_id)
        if result:
            self._audit.record_delete(
                ENTITY_CHARGE,
                charge_id,
                actor_id,
                actor_display_name=actor_name,
                metadata_json=metadata,
            )
        return result

    def get_charge(self, charge_id: int) -> Charge:
        charge = self.charge_repo.get_by_id(charge_id)
        if not charge:
            raise NotFoundError(
                CHARGE_NOT_FOUND.format(charge_id=charge_id), ErrorCode.CHARGE_NOT_FOUND
            )
        return charge
