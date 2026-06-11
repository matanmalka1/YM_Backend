import datetime

from fastapi import APIRouter, Body, Depends, Query, Response, status

from app.charges.schemas.charge import (
    BulkChargeActionRequest,
    BulkChargeActionResponse,
    ChargeCancelRequest,
    ChargeCreateRequest,
    ChargeListResponse,
    ChargeResponse,
)
from app.charges.services.billing_service import BillingService
from app.charges.services.bulk_billing_service import BulkBillingService
from app.charges.services.charge_query_service import ChargeQueryService
from app.charges.services.charge_response_builder import ChargeResponseBuilder
from app.core.exceptions import not_found_response
from app.infrastructure.idempotency import IdempotencyGuard, require_idempotency_key
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/charges",
    tags=["charges"],
)


def _response_builder(db: DBSession) -> ChargeResponseBuilder:
    return ChargeResponseBuilder(ChargeQueryService(db))


@router.post(
    "",
    response_model=ChargeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def create_charge(request: ChargeCreateRequest, db: DBSession, user: CurrentUser):
    charge = BillingService(db).create_charge(
        client_record_id=request.client_record_id,
        business_id=request.business_id,
        amount=request.amount,
        charge_type=request.charge_type,
        period=request.period,
        months_covered=request.months_covered,
        actor_id=user.id,
    )
    return _response_builder(db).build(charge, user.role)


@router.post(
    "/{charge_id}/issue",
    response_model=ChargeResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החיוב המבוקש לא נמצא"),
)
def issue_charge(charge_id: int, db: DBSession, user: CurrentUser):
    charge = BillingService(db).issue_charge(charge_id, actor_id=user.id)
    return _response_builder(db).build(charge, user.role)


@router.post(
    "/{charge_id}/mark-paid",
    response_model=ChargeResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החיוב המבוקש לא נמצא"),
)
def mark_charge_paid(charge_id: int, db: DBSession, user: CurrentUser):
    charge = BillingService(db).mark_charge_paid(charge_id, actor_id=user.id)
    return _response_builder(db).build(charge, user.role)


@router.post(
    "/{charge_id}/cancel",
    response_model=ChargeResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החיוב המבוקש לא נמצא"),
)
def cancel_charge(
    charge_id: int,
    db: DBSession,
    user: CurrentUser,
    request: ChargeCancelRequest = Body(default_factory=ChargeCancelRequest),
):
    charge = BillingService(db).cancel_charge(charge_id, actor_id=user.id, reason=request.reason)
    return _response_builder(db).build(charge, user.role)


@router.get(
    "",
    response_model=ChargeListResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def list_charges(
    db: DBSession,
    user: CurrentUser,
    business_id: int | None = None,
    client_record_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    charge_type: str | None = None,
    period: str | None = None,
    issued_after: datetime.date | None = None,
    issued_before: datetime.date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ChargeQueryService(db).list_charges_paginated(
        business_id=business_id,
        client_record_id=client_record_id,
        status=status_filter,
        charge_type=charge_type,
        period=period,
        issued_after=issued_after,
        issued_before=issued_before,
        page=page,
        page_size=page_size,
        user_role=user.role,
    )


@router.get(
    "/{charge_id}",
    response_model=ChargeResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החיוב המבוקש לא נמצא"),
)
def get_charge(charge_id: int, db: DBSession, user: CurrentUser):
    charge = BillingService(db).get_charge(charge_id)
    return _response_builder(db).build(charge, user.role)


@router.post(
    "/bulk-action",
    response_model=BulkChargeActionResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
def bulk_charge_action(
    request: BulkChargeActionRequest,
    db: DBSession,
    user: CurrentUser,
    idem: IdempotencyGuard = Depends(require_idempotency_key),
):
    service = BulkBillingService(db)

    def _run():
        succeeded, failed = service.bulk_action(
            charge_ids=request.charge_ids,
            action=request.action,
            actor_id=user.id,
            cancellation_reason=request.cancellation_reason,
        )
        return BulkChargeActionResponse(succeeded=succeeded, failed=failed)

    return idem.execute(payload=request.model_dump_json().encode(), fn=_run)


@router.delete(
    "/{charge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
    responses=not_found_response(description="החיוב המבוקש לא נמצא"),
)
def delete_charge(charge_id: int, db: DBSession, user: CurrentUser):
    service = BillingService(db)
    service.delete_charge(charge_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
