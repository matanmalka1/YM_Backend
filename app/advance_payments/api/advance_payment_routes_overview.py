from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.advance_payments.api.advance_payment_responses import (
    ADVANCE_PAYMENT_BULK_MARK_PAID_RESPONSES,
)
from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.advance_payments.schemas.advance_payment import (
    AdvancePaymentOverviewResponse,
    AdvancePaymentOverviewRow,
    AvailableTurnover,
    BulkMarkPaidRequest,
    BulkMarkPaidResponse,
    BulkMarkPaidSkippedItem,
    MonthBatchSummary,
)
from app.advance_payments.services.advance_payment_analytics_service import (
    AdvancePaymentAnalyticsService,
    AdvancePaymentOverviewEnrichedRow,
)
from app.advance_payments.services.advance_payment_service import AdvancePaymentService
from app.core.api_types import SortOrder
from app.core.pagination import MAX_PAGE_SIZE
from app.infrastructure.idempotency import IdempotencyGuard, require_idempotency_key
from app.users.api.user_deps import CurrentUser, DBSession, require_role
from app.users.models.user import UserRole


def _to_overview_row(row: AdvancePaymentOverviewEnrichedRow) -> AdvancePaymentOverviewRow:
    available = AvailableTurnover.from_resolution(row.available_turnover)
    return AdvancePaymentOverviewRow(
        id=row.payment.id,
        client_record_id=row.payment.client_record_id,
        office_client_number=row.office_client_number,
        client_name=row.client_name,
        id_number=row.id_number,
        period=row.payment.period,
        period_months_count=row.payment.period_months_count,
        due_date=row.payment.due_date,
        due_date_effective=row.payment.due_date_effective,
        expected_amount=row.payment.expected_amount,
        paid_amount=row.payment.paid_amount,
        status=row.payment.status,
        payment_method=row.payment.payment_method,
        payment_reference=row.payment.payment_reference,
        vat_turnover_mismatch=row.vat_turnover_mismatch,
        turnover_amount=row.payment.turnover_amount,
        turnover_source=row.payment.turnover_source,
        turnover_snapshot_at=row.payment.turnover_snapshot_at,
        calculated_amount=row.payment.calculated_amount,
        override_amount=row.payment.override_amount,
        available_turnover=available,
        missing_turnover=row.payment.turnover_amount is None and available is None,
        advance_rate=row.advance_rate,
    )


overview_router = APIRouter(
    prefix="/advance-payments",
    tags=["advance-payments"],
    dependencies=[Depends(require_role(UserRole.ADVISOR, UserRole.SECRETARY))],
)


@overview_router.get("/overview", response_model=AdvancePaymentOverviewResponse)
def list_advance_payments_overview(
    db: DBSession,
    user: CurrentUser,
    year: int = Query(...),
    month: int | None = Query(None, ge=1, le=12),
    due_date: date | None = Query(None),
    period_months_count: int | None = Query(None, ge=1, le=2),
    client_record_id: int | None = Query(None),
    client_search: str | None = Query(None),
    status: list[AdvancePaymentStatus] | None = Query(None),
    timing_status: Literal["overdue", "on_time"] | None = Query(None),
    sort_by: str = Query(
        "client_name",
        pattern="^(client_name|expected_amount|paid_amount|delta)$",
    ),
    order: SortOrder = Query(SortOrder.asc),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
):
    resolved_statuses = status if status else None

    service = AdvancePaymentAnalyticsService(db)
    rows, total = service.list_overview(
        year=year,
        month=month,
        due_date=due_date,
        period_months_count=period_months_count,
        client_record_id=client_record_id,
        client_search=client_search,
        statuses=resolved_statuses,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
        timing_status=timing_status,
    )
    kpis = service.get_overview_kpis(
        year=year,
        month=month,
        statuses=resolved_statuses,
        due_date=due_date,
        period_months_count=period_months_count,
        client_record_id=client_record_id,
        client_search=client_search,
        timing_status=timing_status,
    )

    items = [_to_overview_row(row) for row in rows]
    return AdvancePaymentOverviewResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_expected=kpis["total_expected"],
        total_paid=kpis["total_paid"],
        collection_rate=kpis["collection_rate"],
    )


@overview_router.get("/overview/batches", response_model=list[MonthBatchSummary])
def list_advance_payment_batches(
    db: DBSession,
    user: CurrentUser,
    year: int | None = Query(None),
    client_record_id: int | None = Query(None),
):
    """Unpaginated by design. Returns one summary per (year, month) with a batch.

    Bounded by data, not a fixed cap: <= 12 rows when ``year`` is given,
    otherwise grows with the number of distinct months across history (small).
    """
    return AdvancePaymentAnalyticsService(db).get_month_batches(
        year,
        client_record_id=client_record_id,
    )


@overview_router.post(
    "/bulk-mark-paid",
    response_model=BulkMarkPaidResponse,
    dependencies=[Depends(require_role(UserRole.ADVISOR))],
    responses=ADVANCE_PAYMENT_BULK_MARK_PAID_RESPONSES,
)
def bulk_mark_paid(
    request: BulkMarkPaidRequest,
    db: DBSession,
    user: CurrentUser,
    idem: IdempotencyGuard = Depends(require_idempotency_key),
):
    """Org-level bulk: top up each listed payment to its expected amount.

    ADVISOR-only (mutation), unlike the read routes on this router.
    """
    service = AdvancePaymentService(db)

    def _run():
        updated, skipped = service.bulk_mark_paid(
            request.payment_ids,
            paid_at=request.paid_at,
            payment_method=request.payment_method,
            reference_prefix=request.reference_prefix,
            actor_id=user.id,
            actor_name=user.full_name,
        )
        return BulkMarkPaidResponse(
            updated=updated,
            skipped=[BulkMarkPaidSkippedItem(id=pid, reason=reason) for pid, reason in skipped],
        )

    return idem.execute(payload=request.model_dump_json().encode(), fn=_run)
