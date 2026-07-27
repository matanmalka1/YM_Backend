from collections import defaultdict
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import is_advance_payment_resolved
from app.annual_reports.models.annual_report_enums import is_annual_report_resolved
from app.common.enums import ObligationType
from app.core.pagination import paginate_sequence
from app.tax_calendar.repositories.tax_calendar_grouped_repository import (
    TaxCalendarGroupedRepository,
)
from app.tax_calendar.schemas.tax_calendar_grouped import (
    TaxCalendarGroupListResponse,
    TaxCalendarGroupResponse,
    TaxCalendarGroupsSummary,
)
from app.utils.time_utils import israel_today
from app.vat.models.vat_enums import is_vat_work_item_resolved

# Each domain answers "does this obligation still need work?" for itself. This module
# only routes to the owning domain's predicate; it does not decide. Three literal
# status sets used to live here, so adding a status to any domain silently required
# editing this file to stay correct — and nothing said so.
_RESOLVED_BY_OBLIGATION = {
    ObligationType.VAT: is_vat_work_item_resolved,
    ObligationType.ADVANCE_PAYMENT: is_advance_payment_resolved,
    ObligationType.ANNUAL_REPORT: is_annual_report_resolved,
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
    tax_year_after: int | None,
    tax_year_before: int | None,
    obligation_type: ObligationType | None,
    include_empty: bool,
    client_record_id: int | None = None,
    client_search: str | None = None,
    status: str = "all",
    due_after: date | None = None,
    order: str = "period",
    page: int = 1,
    page_size: int = 25,
) -> TaxCalendarGroupListResponse:
    groups = _build_groups(
        db,
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
        include_empty=include_empty,
        client_record_id=client_record_id,
        client_search=client_search,
    )
    groups = _filter_groups_by_status(groups, status)
    if due_after is not None:
        # A group with no known deadline cannot satisfy "due after X".
        groups = [
            group
            for group in groups
            if group.effective_due_date_min is not None
            and group.effective_due_date_min >= due_after
        ]
    if order == "due":
        # Undated groups sort last: they are real work, but there is no date to place
        # them among the dated ones.
        groups = sorted(
            groups,
            key=lambda group: (
                group.effective_due_date_min is None,
                group.effective_due_date_min or date.min,
            ),
        )
    total = len(groups)
    summary = TaxCalendarGroupsSummary(
        groups=total,
        linked=sum(g.linked_count for g in groups),
        open=sum(g.open_count for g in groups),
        overdue=sum(g.overdue_count for g in groups),
        done=sum(g.done_count for g in groups),
    )
    return TaxCalendarGroupListResponse(
        items=paginate_sequence(groups, page, page_size),
        page=page,
        page_size=page_size,
        total=total,
        summary=summary,
    )


def _build_groups(
    db: Session,
    *,
    tax_year_after: int | None,
    tax_year_before: int | None,
    obligation_type: ObligationType | None,
    include_empty: bool,
    client_record_id: int | None = None,
    client_search: str | None = None,
) -> list[TaxCalendarGroupResponse]:
    repo = TaxCalendarGroupedRepository(db)
    entries = repo.list_entries(
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
    )
    rows_by_entry = _linked_rows_by_entry(
        repo,
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    )
    today = israel_today()

    groups: list[TaxCalendarGroupResponse] = []
    for entry in entries:
        rows = rows_by_entry.get(entry.id, [])
        if not include_empty and not rows:
            continue

        effective_min, effective_max = _effective_due_dates(entry, rows)
        done_count = _done_count(entry.obligation_type, rows)
        open_count = len(rows) - done_count
        # A row with no known deadline cannot be overdue — there is nothing to be
        # late against. It used to inherit the entry's date and be judged by it.
        overdue_count = sum(
            1
            for row in rows
            if not _is_done(entry.obligation_type, row)
            and (due := _row_due_date(entry.obligation_type, row, entry.due_date)) is not None
            and due < today
        )
        groups.append(
            TaxCalendarGroupResponse(
                tax_calendar_entry_id=entry.id,
                obligation_type=entry.obligation_type.value,
                period=entry.period,
                period_months_count=entry.period_months_count,
                tax_year=entry.tax_year,
                regulatory_due_date=_regulatory_due_date(entry),
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
    tax_year_after: int | None,
    tax_year_before: int | None,
    obligation_type: ObligationType | None,
    client_record_id: int | None,
    client_search: str | None = None,
):
    rows = defaultdict(list)
    for row in repo.list_vat_for_entries(
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    ):
        rows[_entry_id(row)].append(row)
    for row in repo.list_advance_for_entries(
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    ):
        rows[_entry_id(row)].append(row)
    for row in repo.list_annual_for_entries(
        tax_year_after=tax_year_after,
        tax_year_before=tax_year_before,
        obligation_type=obligation_type,
        client_record_id=client_record_id,
        client_search=client_search,
    ):
        rows[_entry_id(row)].append(row)
    return rows


def _regulatory_due_date(entry) -> date | None:
    """The one statutory date every client shares for this entry, if there is one.

    There is none for an annual report: the deadline varies by entity type, while an
    annual entry is unique per ``(obligation_type, tax_year)`` — a single row for the
    whole office. Its stored ``due_date`` comes from a seeded rule and describes no
    particular client, so it is not published as one.
    """
    if entry.obligation_type == ObligationType.ANNUAL_REPORT:
        return None
    return entry.due_date


def _effective_due_dates(entry, rows: list) -> tuple[date | None, date | None]:
    """The span of real deadlines among the linked rows.

    ``(None, None)`` when nothing linked has a known deadline — the group has work
    but no date to place it on, which is different from having no work.
    """
    due_dates = [
        due
        for due in (_row_due_date(entry.obligation_type, row, entry.due_date) for row in rows)
        if due is not None
    ]
    if not due_dates:
        return _regulatory_due_date(entry), _regulatory_due_date(entry)
    return min(due_dates), max(due_dates)


def _row_due_date(obligation_type, row, entry_due_date: date) -> date | None:
    """One linked row's effective deadline, or ``None`` when it has none.

    An annual report never falls back to the entry's date. The two come from
    different authorities — ``filing_deadline`` from ``tax_rules_config``, the entry
    from a seeded ``DeadlineRule`` — so borrowing one for the other invents a
    deadline. A CUSTOM-deadline report has ``filing_deadline`` NULL by design and
    genuinely has no computed date.

    VAT and advance rows do fall back, because ``due_date_effective`` is a snapshot
    of that very entry and is null only on legacy rows.
    """
    if obligation_type == ObligationType.ANNUAL_REPORT:
        value = getattr(row, "filing_deadline", None)
        return None if value is None else _date_value(value, entry_due_date)
    return _date_value(getattr(row, "due_date_effective", None), entry_due_date)


def _done_count(obligation_type, rows: list) -> int:
    return sum(1 for row in rows if _is_done(obligation_type, row))


def _is_done(obligation_type, row) -> bool:
    is_resolved = _RESOLVED_BY_OBLIGATION.get(obligation_type)
    if is_resolved is None:
        return False
    return is_resolved(row.status)
