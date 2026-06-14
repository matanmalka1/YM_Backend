"""Analytics, KPI, and overview service for AdvancePayment domain."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.advance_payments.repositories.advance_payment_aggregation_repository import (
    AdvancePaymentAggregationRepository,
)
from app.advance_payments.repositories.advance_payment_batch_repository import (
    AdvancePaymentBatchRepository,
)
from app.advance_payments.repositories.turnover_lookup_repository import (
    TurnoverLookupRepository,
)
from app.advance_payments.schemas.advance_payment import MonthBatchSummary
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import NotFoundError


@dataclass(slots=True, frozen=True)
class AdvancePaymentOverviewEnrichedRow:
    payment: AdvancePayment
    office_client_number: int | None
    business_name: str
    id_number: str | None
    live_turnover: Decimal | None
    advance_rate: Decimal | None


class AdvancePaymentAnalyticsService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AdvancePaymentAggregationRepository(db)

    @staticmethod
    def _collection_rate(total_paid: Decimal, total_expected: Decimal) -> Decimal:
        paid = Decimal(total_paid or 0)
        expected = Decimal(total_expected or 0)
        if expected <= 0:
            return Decimal("0")
        return (paid / expected * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ─── Overview ─────────────────────────────────────────────────────────────

    def list_overview(
        self,
        year: int,
        month: int | None = None,
        statuses: list[AdvancePaymentStatus] | None = None,
        page: int = 1,
        page_size: int = 50,
        client_record_id: int | None = None,
        client_search: str | None = None,
        due_date: date | None = None,
        period_months_count: int | None = None,
    ) -> tuple[list[AdvancePaymentOverviewEnrichedRow], int]:
        if statuses is None:
            statuses = list(AdvancePaymentStatus)

        rows, total = self.repo.list_overview_payment_rows(
            year=year,
            month=month,
            statuses=statuses,
            page=page,
            page_size=page_size,
            client_record_id=client_record_id,
            client_search=client_search,
            due_date=due_date,
            period_months_count=period_months_count,
        )

        turnover_repo = TurnoverLookupRepository(self.db)
        payments = [row.payment for row in rows]
        live_turnover_map = self._build_live_turnover_map(payments, turnover_repo)

        enriched = [
            AdvancePaymentOverviewEnrichedRow(
                payment=row.payment,
                office_client_number=row.office_client_number,
                business_name=row.business_name,
                id_number=row.id_number,
                live_turnover=live_turnover_map.get(
                    (row.payment.client_record_id, row.payment.period)
                ),
                advance_rate=row.payment.advance_rate,
            )
            for row in rows
        ]
        return enriched, total

    @staticmethod
    def _build_live_turnover_map(
        payments: list[AdvancePayment],
        turnover_repo: TurnoverLookupRepository,
    ) -> dict[tuple[int, str], object | None]:
        """Batch-fetch live turnover per (client_record_id, period)."""
        from collections import defaultdict

        by_client: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for p in payments:
            if p.turnover_amount is None:
                by_client[p.client_record_id].append((p.period, p.period_months_count))

        result: dict[tuple[int, str], object | None] = {}
        turnover_by_period = turnover_repo.get_turnover_for_many_clients(dict(by_client))
        for key, (turnover, _) in turnover_by_period.items():
            result[key] = turnover
        return result

    # ─── KPIs ─────────────────────────────────────────────────────────────────

    def get_annual_kpis_for_client(self, client_record_id: int, year: int) -> dict:
        if not ClientRecordRepository(self.db).get_by_id(client_record_id):
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה",
                "ADVANCE_PAYMENT.CLIENT_NOT_FOUND",
            )
        data = self.repo.get_annual_kpis_for_client(client_record_id, year)
        return {
            **data,
            "client_record_id": client_record_id,
            "year": year,
            "collection_rate": self._collection_rate(data["total_paid"], data["total_expected"]),
        }

    def get_overview_kpis(
        self,
        year: int,
        month: int | None = None,
        statuses: list[AdvancePaymentStatus] | None = None,
        due_date: date | None = None,
        period_months_count: int | None = None,
        client_record_id: int | None = None,
        client_search: str | None = None,
    ) -> dict:
        if statuses is None:
            statuses = list(AdvancePaymentStatus)
        data = self.repo.get_overview_kpis(
            year,
            month,
            statuses,
            due_date=due_date,
            period_months_count=period_months_count,
            client_record_id=client_record_id,
            client_search=client_search,
        )
        return {
            **data,
            "collection_rate": self._collection_rate(data["total_paid"], data["total_expected"]),
        }

    # ─── Monthly batches ──────────────────────────────────────────────────────

    def get_month_batches(
        self,
        year: int | None,
        *,
        client_record_id: int | None = None,
    ) -> list[MonthBatchSummary]:
        rows = AdvancePaymentBatchRepository(self.db).batch_summary_by_month(
            year,
            client_record_id=client_record_id,
        )
        result: list[MonthBatchSummary] = []
        for r in rows:
            total_expected = Decimal(r.total_expected or 0)
            total_paid = Decimal(r.total_paid or 0)
            client_count = int(r.client_count)
            paid_count = int(r.paid_count or 0)
            result.append(
                MonthBatchSummary(
                    year=int(r.year),
                    month=int(r.month),
                    due_date=r.due_date,
                    period_months_count=int(r.period_months_count or 1),
                    client_count=client_count,
                    missing_turnover_count=int(r.snapshot_missing_count or 0),
                    overdue_count=int(r.overdue_count or 0),
                    pending_count=int(r.pending_count or 0),
                    paid_count=paid_count,
                    not_paid_count=client_count - paid_count,
                    total_expected=total_expected,
                    total_paid=total_paid,
                    collection_rate=self._collection_rate(total_paid, total_expected),
                )
            )
        return result
