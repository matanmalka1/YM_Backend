from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.annual_reports import models as annual_report_models
from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.vat.repositories.vat_compliance_repository import (
    VatComplianceRepository,
)
from app.work_queue.schemas.work_queue import WorkQueueItem, WorkQueueSourceType
from app.work_queue.services.work_queue_common import UPCOMING_WINDOW_DAYS, WorkQueueContext
from app.work_queue.services.work_queue_metadata import (
    annual_report_metadata,
    vat_work_item_metadata,
)

_DONE_ANNUAL_STATUSES = {
    annual_report_models.AnnualReportStatus.SUBMITTED,
    annual_report_models.AnnualReportStatus.CLOSED,
    annual_report_models.AnnualReportStatus.CANCELED,
}


def _vat_due_date(item) -> date:
    due_date_effective = item.due_date_effective
    if due_date_effective is None:
        raise ValueError(f"VatWorkItem {item.id} is missing due_date_effective")
    return due_date_effective.date() if hasattr(due_date_effective, "date") else due_date_effective


def vat_work_item_items(ctx: WorkQueueContext, client_record_id: int | None) -> list[WorkQueueItem]:
    """Return work-queue items for unfiled VAT periods.

    get_overdue_unfiled returns full VatWorkItem objects — no per-row query.
    """
    vat_items = [
        vat_item
        for vat_item in VatComplianceRepository(ctx.db).get_overdue_unfiled(ctx.today)
        if client_record_id is None or vat_item.client_record_id == client_record_id
    ]
    ctx.preload_client_identities(vat_item.client_record_id for vat_item in vat_items)

    items = []
    for vat_item in vat_items:
        due_date = _vat_due_date(vat_item)
        metadata = vat_work_item_metadata(vat_item, due_date)
        items.append(
            ctx.item(
                WorkQueueSourceType.VAT_WORK_ITEM,
                vat_item.id,
                f'מע"מ לא הוגש: {metadata["period_label"]}',
                due_date,
                vat_item.client_record_id,
                status_label=vat_item.status.value
                if hasattr(vat_item.status, "value")
                else str(vat_item.status),
                metadata=metadata,
            )
        )
    return items


def annual_report_items(ctx: WorkQueueContext, client_record_id: int | None) -> list[WorkQueueItem]:
    cutoff = ctx.today + timedelta(days=UPCOMING_WINDOW_DAYS)
    annual_report = annual_report_models.AnnualReport
    stmt = scope_to_active_clients_stmt(select(annual_report), annual_report).where(
        annual_report.deleted_at.is_(None),
        annual_report.filing_deadline.isnot(None),
        annual_report.filing_deadline <= cutoff,
        annual_report.status.notin_([s.value for s in _DONE_ANNUAL_STATUSES]),
    )
    if client_record_id is not None:
        stmt = stmt.where(annual_report.client_record_id == client_record_id)
    reports = list(ctx.db.scalars(stmt))
    ctx.preload_client_identities(report.client_record_id for report in reports)
    return [_annual_report_item(ctx, report) for report in reports]


def _annual_report_item(ctx: WorkQueueContext, report) -> WorkQueueItem:
    due_date = (
        report.filing_deadline.date()
        if hasattr(report.filing_deadline, "date")
        else report.filing_deadline
    )
    return ctx.item(
        WorkQueueSourceType.ANNUAL_REPORT,
        report.id,
        f"דוח שנתי {report.tax_year}",
        due_date,
        report.client_record_id,
        status_label=report.status.value if hasattr(report.status, "value") else str(report.status),
        metadata=annual_report_metadata(report),
    )
