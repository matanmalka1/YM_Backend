import logging

from fastapi import APIRouter, Depends, Query, status

from app.advance_payments.api.responses import (
    ADVANCE_PAYMENT_CREATE_RESPONSES,
    ADVANCE_PAYMENT_UPDATE_RESPONSES,
)
from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.repositories.turnover_lookup_repository import (
    TurnoverLookupRepository,
)
from app.advance_payments.schemas.advance_payment import (
    AdvancePaymentCreateRequest,
    AdvancePaymentListResponse,
    AdvancePaymentRow,
    AdvancePaymentUpdateRequest,
    AnnualKPIResponse,
    PrefillTurnoverResponse,
)
from app.advance_payments.services.advance_payment_analytics_service import (
    AdvancePaymentAnalyticsService,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.common.period_utils import parse_period_year
from app.core.openapi_responses import not_found_response
from app.core.pagination import MAX_PAGE_SIZE
from app.users.api.deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole

router = APIRouter(
    prefix="/clients/{client_record_id}/advance-payments",
    tags=["advance-payments"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=AdvancePaymentListResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def list_advance_payments(
    client_record_id: int,
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
    live_map = (
        turnover_repo.get_turnover_for_many(client_record_id, period_list) if period_list else {}
    )

    def _to_row(p) -> AdvancePaymentRow:
        live, _ = (
            live_map.get(p.period, (None, None)) if p.turnover_amount is None else (None, None)
        )
        row = AdvancePaymentRow.model_validate(p)
        row.live_turnover = live
        row.missing_turnover = p.turnover_amount is None and live is None
        return row

    return AdvancePaymentListResponse(
        items=[_to_row(p) for p in items],
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
    client_record_id: int,
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
        annual_report_id=request.annual_report_id,
        notes=request.notes,
    )
    return AdvancePaymentRow.model_validate(payment)


@router.get(
    "/prefill-turnover",
    response_model=PrefillTurnoverResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_prefill_turnover(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
    period: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    period_months_count: int = Query(..., ge=1, le=2),
):
    t, vid, src = AdvancePaymentService(db).get_prefill_turnover_for_client(
        client_record_id, period, period_months_count
    )
    return PrefillTurnoverResponse(
        period=period,
        period_months_count=period_months_count,
        turnover_amount=t,
        vat_work_item_id=vid,
        source=src,
    )


@router.get(
    "/kpi",
    response_model=AnnualKPIResponse,
    responses=not_found_response(description="הלקוח המבוקש לא נמצא"),
)
def get_annual_kpis(
    client_record_id: int,
    db: DBSession,
    user: CurrentUser,
    year: int = Query(...),
):
    service = AdvancePaymentAnalyticsService(db)
    data = service.get_annual_kpis_for_client(client_record_id=client_record_id, year=year)
    return AnnualKPIResponse(**data)


@router.patch(
    "/{payment_id}",
    response_model=AdvancePaymentRow,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_UPDATE_RESPONSES,
)
def update_advance_payment(
    client_record_id: int,
    payment_id: int,
    request: AdvancePaymentUpdateRequest,
    db: DBSession,
    user: CurrentUser,
):
    service = AdvancePaymentService(db)
    payment = service.update_payment_for_client(
        client_record_id=client_record_id,
        payment_id=payment_id,
        **request.model_dump(exclude_unset=True),
    )
    # When a payment is marked PAID, invalidate any open annual report tax calculation
    # for the same client+year so the advisor is prompted to re-save after recalculation.
    if payment.status == AdvancePaymentStatus.PAID and payment.period:
        tax_year: int | None = None
        try:
            tax_year = parse_period_year(payment.period)
            from app.annual_reports.services.tax_service import (
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


@router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=not_found_response(description="תשלום המקדמה המבוקש לא נמצא"),
)
def delete_advance_payment(
    client_record_id: int,
    payment_id: int,
    db: DBSession,
    user: CurrentUser,
):
    AdvancePaymentService(db).delete_payment_for_client(
        client_record_id, payment_id, actor_id=user.id
    )
