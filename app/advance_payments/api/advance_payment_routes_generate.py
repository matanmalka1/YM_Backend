from fastapi import APIRouter, Depends, status

from app.advance_payments.api.advance_payment_responses import ADVANCE_PAYMENT_GENERATE_RESPONSES
from app.advance_payments.schemas.advance_payment import (
    GenerateScheduleRequest,
    GenerateScheduleResponse,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients/{client_record_id}/advance-payments",
    tags=["advance-payments"],
)


@router.post(
    "/generate",
    response_model=GenerateScheduleResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_GENERATE_RESPONSES,
)
def generate_advance_payment_schedule(
    client_record_id: PathId,
    request: GenerateScheduleRequest,
    db: DBSession,
    user: CurrentUser,
):
    created, skipped = AdvancePaymentService(db).generate_annual_schedule(
        client_record_id,
        request.year,
        period_months_count=request.period_months_count,
        reference_date=request.reference_date,
        actor_id=user.id,
        actor_name=user.full_name,
    )
    return GenerateScheduleResponse(created=len(created), skipped=skipped)
