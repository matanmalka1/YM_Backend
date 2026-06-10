from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
)
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder, BinderLocationStatus
from app.charges.models.charge import Charge, ChargeStatus
from app.common.source_types import WorkQueueSourceType, source_route
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem


@dataclass(frozen=True)
class SourceState:
    source_type: WorkQueueSourceType
    source_id: int
    label: str
    client_record_id: int | None
    status: str | None
    is_missing: bool = False
    is_deleted: bool = False
    is_final: bool = False
    route: str | None = None


def _state(
    source_type: WorkQueueSourceType,
    source_id: int,
    label: str,
    client_record_id: int | None,
    status,
    *,
    is_deleted: bool,
    is_final: bool,
    route: str | None = None,
) -> SourceState:
    status_value = status.value if hasattr(status, "value") else status
    return SourceState(
        source_type=source_type,
        source_id=source_id,
        label=label,
        client_record_id=client_record_id,
        status=status_value,
        is_deleted=is_deleted,
        is_final=is_final,
        route=route,
    )


def load_source_states(
    db: Session, keys: Iterable[tuple[WorkQueueSourceType, int]]
) -> dict[tuple[str, int], SourceState]:
    key_list = list(keys)
    grouped: dict[WorkQueueSourceType, set[int]] = {}
    for source_type, source_id in key_list:
        grouped.setdefault(source_type, set()).add(source_id)

    states: dict[tuple[str, int], SourceState] = {}

    ids = grouped.get(WorkQueueSourceType.VAT_WORK_ITEM, set())
    if ids:
        rows = db.scalars(select(VatWorkItem).where(VatWorkItem.id.in_(ids))).all()
        for row in rows:
            states[(WorkQueueSourceType.VAT_WORK_ITEM.value, row.id)] = _state(
                WorkQueueSourceType.VAT_WORK_ITEM,
                row.id,
                f'מע"מ {row.period}',
                row.client_record_id,
                row.status,
                is_deleted=row.deleted_at is not None,
                is_final=row.status
                in {
                    VatWorkItemStatus.FILED,
                    VatWorkItemStatus.CANCELED,
                },
                route=source_route(WorkQueueSourceType.VAT_WORK_ITEM, row.id),
            )

    ids = grouped.get(WorkQueueSourceType.ANNUAL_REPORT, set())
    if ids:
        rows = db.scalars(select(AnnualReport).where(AnnualReport.id.in_(ids))).all()
        for row in rows:
            states[(WorkQueueSourceType.ANNUAL_REPORT.value, row.id)] = _state(
                WorkQueueSourceType.ANNUAL_REPORT,
                row.id,
                f"דוח שנתי {row.tax_year}",
                row.client_record_id,
                row.status,
                is_deleted=row.deleted_at is not None,
                is_final=row.status
                in {
                    AnnualReportStatus.SUBMITTED,
                    AnnualReportStatus.CLOSED,
                    AnnualReportStatus.CANCELED,
                },
                route=source_route(WorkQueueSourceType.ANNUAL_REPORT, row.id),
            )

    ids = grouped.get(WorkQueueSourceType.ADVANCE_PAYMENT, set())
    if ids:
        rows = db.scalars(select(AdvancePayment).where(AdvancePayment.id.in_(ids))).all()
        for row in rows:
            states[(WorkQueueSourceType.ADVANCE_PAYMENT.value, row.id)] = _state(
                WorkQueueSourceType.ADVANCE_PAYMENT,
                row.id,
                f"מקדמה {row.period}",
                row.client_record_id,
                row.status,
                is_deleted=row.deleted_at is not None,
                is_final=row.status == AdvancePaymentStatus.PAID,
                route=source_route(WorkQueueSourceType.ADVANCE_PAYMENT, row.id),
            )

    ids = grouped.get(WorkQueueSourceType.CHARGE, set())
    if ids:
        rows = db.scalars(select(Charge).where(Charge.id.in_(ids))).all()
        for row in rows:
            states[(WorkQueueSourceType.CHARGE.value, row.id)] = _state(
                WorkQueueSourceType.CHARGE,
                row.id,
                "חיוב",
                row.client_record_id,
                row.status,
                is_deleted=row.deleted_at is not None,
                is_final=row.status in {ChargeStatus.PAID, ChargeStatus.CANCELED},
                route=source_route(WorkQueueSourceType.CHARGE, row.id),
            )

    ids = grouped.get(WorkQueueSourceType.BINDER, set())
    if ids:
        rows = db.scalars(select(Binder).where(Binder.id.in_(ids))).all()
        for row in rows:
            states[(WorkQueueSourceType.BINDER.value, row.id)] = _state(
                WorkQueueSourceType.BINDER,
                row.id,
                f"קלסר {row.binder_number}",
                row.client_record_id,
                row.location_status,
                is_deleted=row.deleted_at is not None,
                is_final=row.location_status == BinderLocationStatus.HANDED_OVER,
                route=source_route(WorkQueueSourceType.BINDER, row.id),
            )

    for source_type, source_id in key_list:
        states.setdefault(
            (source_type.value, source_id),
            SourceState(
                source_type=source_type,
                source_id=source_id,
                label=f"{source_type.value}:{source_id}",
                client_record_id=None,
                status=None,
                is_missing=True,
                route=source_route(source_type, source_id),
            ),
        )

    return states


__all__ = ["SourceState", "load_source_states"]
