"""Grouped/due-date-level queries for VatWorkItem."""

from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.common.enums import VatType
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_filters import (
    apply_vat_work_item_filters,
)
from app.utils.time_utils import israel_today


def _active_base():
    return scope_to_active_clients_stmt(select(VatWorkItem), VatWorkItem).where(
        VatWorkItem.deleted_at.is_(None)
    )


def list_due_date_groups(
    db: Session,
    *,
    period_type: VatType | None = None,
    client_record_ids: list[int] | None = None,
    status: VatWorkItemStatus | None = None,
    year: int | None = None,
) -> list[dict]:
    """One summary dict per operational due date.

    Uses two projection queries instead of loading ORM objects:
    1. Aggregated counts per due_date_effective.
    2. Distinct (due_date_effective, period, period_type) pairs to build periods[].
    """
    today = israel_today()

    filed = VatWorkItemStatus.FILED
    canceled = VatWorkItemStatus.CANCELED

    # ── Query 1: aggregated counts per due_date_effective ────────────────────
    counts_stmt = apply_vat_work_item_filters(
        scope_to_active_clients_stmt(
            select(
                VatWorkItem.due_date_effective,
                func.count(VatWorkItem.id).label("total_count"),
                func.sum(case((VatWorkItem.status == filed, 1), else_=0)).label("filed_count"),
                func.sum(
                    case((VatWorkItem.status == VatWorkItemStatus.PENDING_MATERIALS, 1), else_=0)
                ).label("pending_count"),
                func.sum(
                    case(
                        (VatWorkItem.status.notin_([filed, canceled]), 1),
                        else_=0,
                    )
                ).label("not_filed_count"),
                func.sum(
                    case(
                        (
                            VatWorkItem.status.notin_([filed, canceled])
                            & (VatWorkItem.due_date_effective < today),
                            1,
                        ),
                        else_=0,
                    )
                ).label("overdue_count"),
            ),
            VatWorkItem,
        ).where(VatWorkItem.deleted_at.is_(None)),
        period_type=period_type,
        client_record_ids=client_record_ids,
    )
    if year is not None:
        counts_stmt = counts_stmt.where(VatWorkItem.period.startswith(f"{year}-"))
    if status is not None:
        counts_stmt = counts_stmt.where(VatWorkItem.status == status)
    counts_stmt = counts_stmt.where(VatWorkItem.due_date_effective.is_not(None)).group_by(
        VatWorkItem.due_date_effective
    )

    count_rows = db.execute(counts_stmt).all()
    if not count_rows:
        return []

    # ── Query 2: distinct (due_date_effective, period, period_type) pairs ────
    periods_stmt = apply_vat_work_item_filters(
        scope_to_active_clients_stmt(
            select(
                VatWorkItem.due_date_effective,
                VatWorkItem.period,
                VatWorkItem.period_type,
            ).distinct(),
            VatWorkItem,
        ).where(VatWorkItem.deleted_at.is_(None)),
        period_type=period_type,
        client_record_ids=client_record_ids,
    )
    if year is not None:
        periods_stmt = periods_stmt.where(VatWorkItem.period.startswith(f"{year}-"))
    if status is not None:
        periods_stmt = periods_stmt.where(VatWorkItem.status == status)
    periods_stmt = periods_stmt.where(VatWorkItem.due_date_effective.is_not(None))

    period_rows = db.execute(periods_stmt).all()

    # ── Assemble periods[] per due_date ───────────────────────────────────────
    periods_by_due: dict[date, list[dict]] = {}
    for row in period_rows:
        periods_by_due.setdefault(row.due_date_effective, []).append(
            {"period": row.period, "period_type": row.period_type}
        )

    for period_list in periods_by_due.values():
        period_list.sort(
            key=lambda p: (0 if p["period_type"] == VatType.BIMONTHLY else 1, p["period"])
        )

    # ── Build result dicts ────────────────────────────────────────────────────
    groups = []
    for row in count_rows:
        dd = row.due_date_effective
        period_list = periods_by_due.get(dd, [])
        # representative period/period_type from the first entry in sorted periods[]
        first = period_list[0] if period_list else {"period": None, "period_type": None}
        groups.append(
            {
                "group_key": dd.isoformat(),
                "due_date": dd,
                "period": first["period"],
                "period_type": first["period_type"],
                "periods": period_list,
                "total_count": int(row.total_count),
                "filed_count": int(row.filed_count),
                "pending_count": int(row.pending_count),
                "not_filed_count": int(row.not_filed_count),
                "overdue_count": int(row.overdue_count),
            }
        )

    return sorted(groups, key=lambda g: g["due_date"])


def list_by_due_date_paginated(
    db: Session,
    due_date: date,
    *,
    page: int = 1,
    page_size: int = 50,
    client_record_ids: list[int] | None = None,
    status: VatWorkItemStatus | None = None,
) -> tuple[list[VatWorkItem], int]:
    count_stmt = apply_vat_work_item_filters(
        scope_to_active_clients_stmt(select(func.count(VatWorkItem.id)), VatWorkItem).where(
            VatWorkItem.deleted_at.is_(None)
        ),
        client_record_ids=client_record_ids,
    )
    stmt = apply_vat_work_item_filters(
        _active_base(),
        client_record_ids=client_record_ids,
    )
    if status is not None:
        count_stmt = count_stmt.where(VatWorkItem.status == status)
        stmt = stmt.where(VatWorkItem.status == status)

    count_stmt = count_stmt.where(VatWorkItem.due_date_effective == due_date)
    stmt = stmt.where(VatWorkItem.due_date_effective == due_date)
    start = (page - 1) * page_size
    items = db.scalars(
        stmt.order_by(VatWorkItem.client_record_id.asc()).offset(start).limit(page_size)
    ).all()
    return list(items), int(db.scalar(count_stmt) or 0)
