from __future__ import annotations

from datetime import date, timedelta

from app.annual_reports.repositories.annual_report_report_repository import (
    AnnualReportRootRepository,
)
from app.vat.repositories.vat_compliance_repository import (
    VatComplianceRepository,
)
from app.work_queue.items.common import UPCOMING_WINDOW_DAYS, WorkQueueContext
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.work_queue_metadata import (
    annual_report_metadata,
    vat_work_item_metadata,
)


def _vat_due_date(item) -> date | None:
    due_date_effective = item.due_date_effective
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
                item_urgency=WorkQueueUrgency.IMPORTANT if due_date is None else None,
                status_label=vat_item.status.value
                if hasattr(vat_item.status, "value")
                else str(vat_item.status),
                metadata=metadata,
            )
        )
    return items


def annual_report_items(ctx: WorkQueueContext, client_record_id: int | None) -> list[WorkQueueItem]:
    cutoff = ctx.today + timedelta(days=UPCOMING_WINDOW_DAYS)
    reports = AnnualReportRootRepository(ctx.db).list_due_for_work_queue(cutoff, client_record_id)
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
