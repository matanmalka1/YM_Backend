import logging

from fastapi import APIRouter, Depends, Query, status

from app.advance_payments.api.advance_payment_responses import (
    ADVANCE_PAYMENT_BULK_REFRESH_TURNOVER_RESPONSES,
    ADVANCE_PAYMENT_CREATE_RESPONSES,
    ADVANCE_PAYMENT_REFRESH_TURNOVER_RESPONSES,
    ADVANCE_PAYMENT_UPDATE_RESPONSES,
)
from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.advance_payment_turnover_lookup_repository import (
    TurnoverLookupRepository,
    TurnoverResolution,
)
from app.advance_payments.schemas.advance_payment import (
    AdvancePaymentCreateRequest,
    AdvancePaymentListResponse,
    AdvancePaymentRow,
    AdvancePaymentUpdateRequest,
    AnnualKPIResponse,
    AvailableTurnover,
    BulkRefreshTurnoverRequest,
    BulkRefreshTurnoverResponse,
    RefreshTurnoverRequest,
)
from app.advance_payments.services.advance_payment_analytics_service import (
    AdvancePaymentAnalyticsService,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.period_utils import parse_period_year
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.core.path_params import PathId
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients/{client_record_id}/advance-payments",
    tags=["advance-payments"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
logger = logging.getLogger(__name__)


def _to_row(payment, resolution: TurnoverResolution | None = None) -> AdvancePaymentRow:
    """Only unsnapshotted periods advertise an available turnover."""
    row = AdvancePaymentRow.model_validate(payment)
    row.available_turnover = AvailableTurnover.from_resolution(resolution)
    row.missing_turnover = payment.turnover_amount is None and row.available_turnover is None
    return row


@router.get(
    "",
    response_model=AdvancePaymentListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_advance_payments(
    client_record_id: PathId,
    db: DBSession,
    user: CurrentUser,
    year: int | None = Query(None),
    status_filter: list[AdvancePaymentStatus] = Query(default=[], alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    service = AdvancePaymentService(db)
    items, total = service.list_payments_for_client(
        client_record_id,
        year,
        status=status_filter if status_filter else None,
        page=page,
        page_size=page_size,
    )
    turnover_repo = TurnoverLookupRepository(db)
    period_list = [(p.period, p.period_months_count) for p in items if p.turnover_amount is None]
    resolved = turnover_repo.resolve_turnover_for_client(client_record_id, period_list)

    def _to_list_row(p) -> AdvancePaymentRow:
        return _to_row(p, resolved.get(p.period) if p.turnover_amount is None else None)

    return AdvancePaymentListResponse(
        items=[_to_list_row(p) for p in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "",
    response_model=AdvancePaymentRow,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_CREATE_RESPONSES,
)
def create_advance_payment(
    client_record_id: PathId,
    request: AdvancePaymentCreateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = AdvancePaymentService(db)
    payment = service.create_payment_for_client(
        client_record_id=client_record_id,
        period=request.period,
        period_months_count=request.period_months_count,
        turnover_amount=request.turnover_amount,
        advance_rate=request.advance_rate,
        override_amount=request.override_amount,
        paid_amount=request.paid_amount,
        payment_method=request.payment_method,
        payment_reference=request.payment_reference,
        annual_report_id=request.annual_report_id,
        notes=request.notes,
        actor_id=user.id,
        actor_name=user.full_name,
    )
    return AdvancePaymentRow.model_validate(payment)


@router.post(
    "/refresh-turnover",
    response_model=BulkRefreshTurnoverResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_BULK_REFRESH_TURNOVER_RESPONSES,
)
def refresh_advance_payment_turnover_bulk(
    client_record_id: PathId,
    request: BulkRefreshTurnoverRequest,
    db: DBSession,
    user: CurrentUser,
):
    """Snapshot every listed period that has a fully filed VAT return.

    Not atomic: periods that cannot be snapshotted are counted, not raised, so
    one period without a return does not block its neighbours.
    """
    result = AdvancePaymentService(db).refresh_turnover_bulk(
        client_record_id,
        request.payment_ids,
        actor_id=user.id,
        actor_name=user.full_name,
    )
    return BulkRefreshTurnoverResponse(
        refreshed=result.refreshed,
        skipped_no_vat=result.skipped_no_vat,
        skipped_not_filed=result.skipped_not_filed,
        skipped_paid=result.skipped_paid,
    )


@router.get(
    "/kpi",
    response_model=AnnualKPIResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_annual_kpis(
    client_record_id: PathId,
    db: DBSession,
    user: CurrentUser,
    year: int = Query(...),
):
    service = AdvancePaymentAnalyticsService(db)
    data = service.get_annual_kpis_for_client(client_record_id=client_record_id, year=year)
    return AnnualKPIResponse(**data)


@router.get(
    "/{payment_id}",
    response_model=AdvancePaymentRow,
    responses=not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
)
def get_advance_payment(
    client_record_id: PathId,
    payment_id: PathId,
    db: DBSession,
    user: CurrentUser,
):
    payment = AdvancePaymentService(db).get_payment_for_client(client_record_id, payment_id)
    resolution = None
    if payment.turnover_amount is None:
        resolution = TurnoverLookupRepository(db).resolve_turnover(
            client_record_id, payment.period, payment.period_months_count
        )
    return _to_row(payment, resolution)


@router.patch(
    "/{payment_id}",
    response_model=AdvancePaymentRow,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_UPDATE_RESPONSES,
)
def update_advance_payment(
    client_record_id: PathId,
    payment_id: PathId,
    request: AdvancePaymentUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = AdvancePaymentService(db)
    payment = service.update_payment_for_client(
        client_record_id=client_record_id,
        payment_id=payment_id,
        actor_id=user.id,
        actor_name=user.full_name,
        **request.model_dump(exclude_unset=True),
    )
    # When a payment is marked PAID, invalidate any open annual report tax calculation
    # for the same client+year so the advisor is prompted to re-save after recalculation.
    if payment.status == AdvancePaymentStatus.PAID and payment.period:
        tax_year: int | None = None
        try:
            tax_year = parse_period_year(payment.period)
            from app.annual_reports.services.annual_report_tax_service import (
                AnnualReportTaxService,
            )

            AnnualReportTaxService(db).invalidate_tax_if_open(client_record_id, tax_year)
        except Exception:
            logger.exception(
                "Failed to invalidate annual report tax after advance payment update. "
                "client_record_id=%s tax_year=%s payment_id=%s period=%s",
                client_record_id,
                tax_year,
                payment_id,
                payment.period,
            )
    return AdvancePaymentRow.model_validate(payment)


@router.post(
    "/{payment_id}/refresh-turnover",
    response_model=AdvancePaymentRow,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_REFRESH_TURNOVER_RESPONSES,
)
def refresh_advance_payment_turnover(
    client_record_id: PathId,
    payment_id: PathId,
    request: RefreshTurnoverRequest,
    db: DBSession,
    user: CurrentUser,
):
    payment = AdvancePaymentService(db).refresh_turnover_from_vat(
        client_record_id,
        payment_id,
        confirm_pending=request.confirm_pending,
        actor_id=user.id,
        actor_name=user.full_name,
    )
    return AdvancePaymentRow.model_validate(payment)


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
)
def delete_advance_payment(
    client_record_id: PathId,
    payment_id: PathId,
    db: DBSession,
    user: CurrentUser,
):
    AdvancePaymentService(db).delete_payment_for_client(
        client_record_id, payment_id, actor_id=user.id, actor_name=user.full_name
    )
