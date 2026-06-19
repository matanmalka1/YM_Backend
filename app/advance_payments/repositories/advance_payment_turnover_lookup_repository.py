"""VAT turnover lookup for advance payment context."""

from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem

# Only FILED items represent settled, authoritative turnover figures.
_FINAL_STATUSES = [VatWorkItemStatus.FILED]
_PENDING_STATUSES = [VatWorkItemStatus.READY_FOR_REVIEW]


def _expand_period(period: str, months_count: int) -> list[str]:
    year = int(period[:4])
    month = int(period[5:7])
    result = []
    for offset in range(months_count):
        absolute = year * 12 + month - 1 + offset
        result_year = absolute // 12
        result_month = absolute % 12 + 1
        result.append(f"{result_year}-{result_month:02d}")
    return result


class TurnoverLookupRepository(BaseRepository[VatWorkItem]):
    """Read total_output_net from vat_work_items for advance payment period."""

    def __init__(self, db: Session):
        self.db = db

    def get_turnover_for_period(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int = 1,
    ) -> tuple[Decimal | None, int | None]:
        """Return (total_output_net, vat_work_item_id) for the period.

        For bi-monthly advances, sums both months' vat_work_items.
        Returns (None, None) if no filed/submitted vat_work_items found.
        """
        periods = _expand_period(period, period_months_count)

        rows = self.db.execute(
            select(VatWorkItem.id, VatWorkItem.total_output_net).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.period.in_(periods),
                VatWorkItem.status.in_(_FINAL_STATUSES),
                VatWorkItem.deleted_at.is_(None),
            )
        ).all()
        if not rows:
            return None, None

        total = sum(Decimal(str(r.total_output_net)) for r in rows)
        # For snapshot FK, use first item (canonical period start)
        primary_id = rows[0].id
        return total, primary_id

    def get_turnover_for_many(
        self,
        client_record_id: int,
        periods: list[tuple[str, int]],
    ) -> dict[str, tuple[Decimal | None, int | None]]:
        """Batch lookup: {period: (turnover, vat_work_item_id)}.

        periods is list of (period_str, period_months_count).
        """
        all_periods = set()
        for period, months_count in periods:
            all_periods.update(_expand_period(period, months_count))

        rows = self.db.execute(
            select(VatWorkItem.id, VatWorkItem.period, VatWorkItem.total_output_net).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.period.in_(all_periods),
                VatWorkItem.status.in_(_FINAL_STATUSES),
                VatWorkItem.deleted_at.is_(None),
            )
        ).all()
        by_period = {r.period: (Decimal(str(r.total_output_net)), r.id) for r in rows}

        result: dict[str, tuple[Decimal | None, int | None]] = {}
        for period, months_count in periods:
            sub_periods = _expand_period(period, months_count)
            found = [by_period[p] for p in sub_periods if p in by_period]
            if not found:
                result[period] = (None, None)
            else:
                total = sum(turnover for turnover, _ in found)
                primary_id = found[0][1]
                result[period] = (total, primary_id)
        return result

    def get_turnover_for_many_clients(
        self,
        periods_by_client: dict[int, list[tuple[str, int]]],
    ) -> dict[tuple[int, str], tuple[Decimal | None, int | None]]:
        """Batch lookup for multiple clients using grouped VAT rows."""
        if not periods_by_client:
            return {}

        all_periods = set()
        client_ids = set(periods_by_client)
        for periods in periods_by_client.values():
            for period, months_count in periods:
                all_periods.update(_expand_period(period, months_count))

        rows = self.db.execute(
            select(
                VatWorkItem.client_record_id,
                VatWorkItem.period,
                func.min(VatWorkItem.id).label("vat_work_item_id"),
                func.coalesce(func.sum(VatWorkItem.total_output_net), 0).label("total_output_net"),
            )
            .where(
                VatWorkItem.client_record_id.in_(client_ids),
                VatWorkItem.period.in_(all_periods),
                VatWorkItem.status.in_(_FINAL_STATUSES),
                VatWorkItem.deleted_at.is_(None),
            )
            .group_by(VatWorkItem.client_record_id, VatWorkItem.period)
        ).all()
        by_client_period = {
            (row.client_record_id, row.period): (
                Decimal(str(row.total_output_net)),
                row.vat_work_item_id,
            )
            for row in rows
        }

        result: dict[tuple[int, str], tuple[Decimal | None, int | None]] = {}
        for client_record_id, periods in periods_by_client.items():
            for period, months_count in periods:
                sub_periods = _expand_period(period, months_count)
                found = [
                    by_client_period[(client_record_id, sub_period)]
                    for sub_period in sub_periods
                    if (client_record_id, sub_period) in by_client_period
                ]
                if not found:
                    result[(client_record_id, period)] = (None, None)
                    continue
                total = sum(turnover for turnover, _ in found)
                primary_id = found[0][1]
                result[(client_record_id, period)] = (total, primary_id)
        return result

    def get_prefill_turnover(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int = 1,  # accepted for API symmetry; VatWorkItem has no period_months_count col
    ) -> tuple[Decimal | None, int | None, Literal["vat_filed", "vat_pending", "none"]]:
        """Return (total_output_net, vat_work_item_id, source) for prefill.

        Checks FILED first, then READY_FOR_REVIEW. Matches by period string only.
        """
        for statuses, source in [
            (_FINAL_STATUSES, "vat_filed"),
            (_PENDING_STATUSES, "vat_pending"),
        ]:
            row = self.db.execute(
                select(VatWorkItem.id, VatWorkItem.total_output_net).where(
                    VatWorkItem.client_record_id == client_record_id,
                    VatWorkItem.period == period,
                    VatWorkItem.status.in_(statuses),
                    VatWorkItem.deleted_at.is_(None),
                )
            ).first()
            if row is not None:
                return Decimal(str(row.total_output_net)), row.id, source
        return None, None, "none"
