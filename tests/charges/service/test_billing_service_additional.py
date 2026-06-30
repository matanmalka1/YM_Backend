import pytest

from app.businesses.models.business import BusinessStatus
from app.charges.models.charge import ChargeStatus, ChargeType
from app.charges.services.charge_billing_service import BillingService
from app.charges.services.charge_query_service import ChargeQueryService
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from tests.helpers.identity import seed_client_with_business


def _business(test_db, *, status: BusinessStatus = BusinessStatus.ACTIVE):
    _client, business = seed_client_with_business(
        test_db,
        full_name="Billing Extra Client",
        id_number=f"BSE{status.value}",
    )
    business.status = status
    test_db.commit()
    return business


def test_billing_service_validation_and_not_found_paths(test_db):
    business = _business(test_db)
    service = BillingService(test_db)

    with pytest.raises(AppError) as amount_exc:
        service.create_charge(
            client_record_id=business.client_id,
            business_id=business.id,
            amount=0,
            charge_type=ChargeType.OTHER,
        )
    assert amount_exc.value.code == "CHARGE.AMOUNT_INVALID"

    with pytest.raises(NotFoundError):
        service.create_charge(
            client_record_id=business.client_id,
            business_id=999999,
            amount=10,
            charge_type=ChargeType.OTHER,
        )

    with pytest.raises(NotFoundError):
        service.mark_charge_paid(999999)
    with pytest.raises(NotFoundError):
        service.cancel_charge(999999)
    with pytest.raises(NotFoundError):
        service.delete_charge(999999)


def test_billing_service_cancel_and_delete_status_guards(test_db):
    business = _business(test_db)
    service = BillingService(test_db)
    charge = service.create_charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=50,
        charge_type=ChargeType.CONSULTATION_FEE,
        actor_id=1,
    )

    service.issue_charge(charge.id, actor_id=1)
    with pytest.raises(AppError):
        service.delete_charge(charge.id)

    canceled = service.cancel_charge(charge.id, actor_id=1)
    assert canceled.status == ChargeStatus.CANCELED
    with pytest.raises(ConflictError):
        service.cancel_charge(charge.id)


def test_create_charge_blocked_for_closed_and_frozen_business(test_db):
    service = BillingService(test_db)
    closed = _business(test_db, status=BusinessStatus.CLOSED)
    frozen = _business(test_db, status=BusinessStatus.FROZEN)

    with pytest.raises(ForbiddenError) as closed_exc:
        service.create_charge(
            client_record_id=closed.client_id,
            business_id=closed.id,
            amount=10,
            charge_type=ChargeType.MONTHLY_RETAINER,
        )
    assert closed_exc.value.code == "BUSINESS.CLOSED"

    with pytest.raises(ForbiddenError) as frozen_exc:
        service.create_charge(
            client_record_id=frozen.client_id,
            business_id=frozen.id,
            amount=10,
            charge_type=ChargeType.MONTHLY_RETAINER,
        )
    assert frozen_exc.value.code == "BUSINESS.FROZEN"


def test_list_charges_exposes_amount_to_all_roles(test_db):
    business = _business(test_db)
    BillingService(test_db).create_charge(
        client_record_id=business.client_id,
        business_id=business.id,
        amount=77,
        charge_type=ChargeType.CONSULTATION_FEE,
        actor_id=1,
    )

    query = ChargeQueryService(test_db)
    result = query.list_charges_paginated(page=1, page_size=10)
    assert result.items
    assert hasattr(result.items[0], "amount")
    assert result.items[0].amount is not None
