from collections import defaultdict
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.common.enums import ObligationType
from app.tax_calendar.repositories.grouped_repository import (
    TaxCalendarGroupedRepository,
)
from app.tax_calendar.schemas.grouped import (
    TaxCalendarGroupListResponse,
    TaxCalendarGroupResponse,
    TaxCalendarGroupsSummary,
)
from app.vat.models.vat_enums import VatWorkItemStatus

VAT_DONE = {VatWorkItemStatus.FILED}
ADVANCE_DONE = {AdvancePaymentStatus.PAID}
ANNUAL_DONE = {
    AnnualReportStatus.SUBMITTED,
    AnnualReportStatus.CLOSED,
    AnnualReportStatus.CANCELED,
}


def _date_value(value, fallback: date) -> date:
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    return value


def _entry_id(row) -> int:
    value = row.tax_calendar_entry_id
    if value is None:
        raise ValueError("tax_calendar_entry_id is required for grouped rows")
    return int(value)


def list_groups_paginated(
    db: Session,
    *,
    start_year: int | None,
    end_year: int | None,
    obligation_type: ObligationType | None,
    include_empty: bool,
    client_record_id: int | None = None,
    client_search: str | None = None,
    status: str = "all",
    page: int = 1,
    page_size: int = 25,
) -> TaxCalendarGroupListResponse:
    groups = _build_groups(
        db,
        start_year=start_year,
        end_year=end_year,
        obligation_type=obligation_type,
        include_empty=include_empty,
        client_record_id=client_record_id,
        client_search=client_search,
    )
    groups = _filter_groups_by_status(groups, status)
    total = len(groups)
    summary = TaxCalendarGroupsSummary(
        groups=total,
        linked=sum(g.linked_count for g in groups),
        open=sum(g.open_count for g in groups),
        overdue=sum(g.overdue_count for g in groups),
        done=sum(g.done_count for g in groups),
    )
    start = (page - 1) * page_size
    return TaxCalendarGroupListResponse(
        items=groups[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
        summary=summary,
    )


def _build_groups(
    db: Session,
    *,
    start_year: int | None,
    end_year: int | None,
    obligation_type: ObligationType | None,
    include_empty: bool,
    client_record_id: int | None = None,
    client_search: str | None = None,
) -> list[TaxCalendarGroupResponse]:
    repo = TaxCalendarGroupedRepository(db)
    entries = repo.list_entries(
        start_year=start_year,
        end_year=end_year,
        obligation_type=obligation_type,
    )
    rows_by_entry = _linked_rows_by_entry(
        repo,
        start_year=start_year,
        end_year=end_year,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    )
    today = date.today()

    groups: list[TaxCalendarGroupResponse] = []
    for entry in entries:
        rows = rows_by_entry.get(entry.id, [])
        if not include_empty and not rows:
            continue

        effective_min, effective_max = _effective_due_dates(entry, rows)
        done_count = _done_count(entry.obligation_type, rows)
        open_count = len(rows) - done_count
        overdue_count = sum(
            1
            for row in rows
            if not _is_done(entry.obligation_type, row)
            and _row_due_date(entry.obligation_type, row, entry.due_date) < today
        )
        groups.append(
            TaxCalendarGroupResponse(
                tax_calendar_entry_id=entry.id,
                obligation_type=entry.obligation_type.value,
                period=entry.period,
                period_months_count=entry.period_months_count,
                tax_year=entry.tax_year,
                regulatory_due_date=entry.due_date,
                effective_due_date_min=effective_min,
                effective_due_date_max=effective_max,
                linked_count=len(rows),
                open_count=open_count,
                done_count=done_count,
                overdue_count=overdue_count,
            )
        )
    return groups


def _filter_groups_by_status(
    groups: list[TaxCalendarGroupResponse], status: str
) -> list[TaxCalendarGroupResponse]:
    if status == "open":
        return [group for group in groups if group.open_count > 0]
    if status == "overdue":
        return [group for group in groups if group.overdue_count > 0]
    if status == "done":
        return [
            group
            for group in groups
            if group.linked_count > 0 and group.open_count == 0 and group.overdue_count == 0
        ]
    return groups


def _linked_rows_by_entry(
    repo: TaxCalendarGroupedRepository,
    *,
    start_year: int | None,
    end_year: int | None,
    obligation_type: ObligationType | None,
    client_record_id: int | None,
    client_search: str | None = None,
):
    rows = defaultdict(list)
    for row in repo.list_vat_for_entries(
        start_year=start_year,
        end_year=end_year,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    ):
        rows[_entry_id(row)].append(row)
    for row in repo.list_advance_for_entries(
        start_year=start_year,
        end_year=end_year,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    ):
        rows[_entry_id(row)].append(row)
    for row in repo.list_annual_for_entries(
        start_year=start_year,
        end_year=end_year,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    ):
        rows[_entry_id(row)].append(row)
    return rows


def _effective_due_dates(entry, rows: list) -> tuple[date, date]:
    if not rows:
        return entry.due_date, entry.due_date
    due_dates = [_row_due_date(entry.obligation_type, row, entry.due_date) for row in rows]
    return min(due_dates), max(due_dates)


def _row_due_date(obligation_type, row, fallback: date) -> date:
    if obligation_type == ObligationType.ANNUAL_REPORT:
        return _date_value(getattr(row, "filing_deadline", None), fallback)
    return _date_value(getattr(row, "due_date_effective", None), fallback)


def _done_count(obligation_type, rows: list) -> int:
    return sum(1 for row in rows if _is_done(obligation_type, row))


def _is_done(obligation_type, row) -> bool:
    if obligation_type == ObligationType.VAT:
        return row.status in VAT_DONE
    if obligation_type == ObligationType.ADVANCE_PAYMENT:
        return row.status in ADVANCE_DONE
    if obligation_type == ObligationType.ANNUAL_REPORT:
        return row.status in ANNUAL_DONE
    return False
