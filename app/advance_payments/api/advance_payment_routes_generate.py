from fastapi import APIRouter, Depends, status

from app.advance_payments.api.advance_payment_responses import ADVANCE_PAYMENT_GENERATE_RESPONSES
from app.advance_payments.schemas.advance_payment import (
    GenerateScheduleRequest,
    GenerateScheduleResponse,
    StaleCadenceSummary,
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
    """Generate a client's annual schedule.

    ``cleanup_stale_cadence`` is opt-in. Without it a client whose frequency
    changed gets a report of the superseded rows blocking the new schedule and
    nothing is deleted; the caller confirms and calls again with the flag.
    """
    service = AdvancePaymentService(db)
    # Counted before generating: a cleanup removes exactly these rows, so the
    # same number is either what is still in the way or what was just removed.
    stale = service.count_stale_cadence(
        client_record_id, request.year, reference_date=request.reference_date
    )
    created, skipped = service.generate_annual_schedule(
        client_record_id,
        request.year,
        period_months_count=request.period_months_count,
        reference_date=request.reference_date,
        actor_id=user.id,
        actor_name=user.full_name,
        cleanup_stale_cadence=request.cleanup_stale_cadence,
    )
    return GenerateScheduleResponse(
        created=len(created),
        skipped=skipped,
        stale_cadence=StaleCadenceSummary(
            removed=stale.pending if request.cleanup_stale_cadence else 0,
            pending=0 if request.cleanup_stale_cadence else stale.pending,
            settled=stale.settled,
        ),
    )
