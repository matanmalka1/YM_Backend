from datetime import date

from sqlalchemy.orm import Session

from app.common.enums import ObligationType
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.pagination import paginate_sequence
from app.tax_calendar.repositories.grouped_repository import (
    TaxCalendarGroupedRepository,
)
from app.tax_calendar.schemas.grouped import (
    TaxCalendarGroupItem,
    TaxCalendarGroupItemsResponse,
)
from app.tax_calendar.services.grouped_service import _is_done, _row_due_date
from app.utils.time_utils import israel_today


def get_group_items(
    db: Session,
    tax_calendar_entry_id: int,
    *,
    page: int = 1,
    page_size: int = 50,
    client_search: str | None = None,
    client_record_id: int | None = None,
) -> TaxCalendarGroupItemsResponse:
    repo = TaxCalendarGroupedRepository(db)
    entry = repo.get_entry(tax_calendar_entry_id)
    if entry is None:
        raise NotFoundError("רשומת יומן מס לא נמצאה", ErrorCode.TAX_CALENDAR_NOT_FOUND)

    rows = _rows_for_entry(
        repo,
        entry,
        client_search=client_search,
        client_record_id=client_record_id,
    )
    today = israel_today()
    items = [
        _to_item(
            source_type=source_type,
            entry=entry,
            row=row,
            client=client,
            client_name=legal_entity.official_name,
            id_number=legal_entity.id_number,
            today=today,
        )
        for source_type, row, client, legal_entity in rows
    ]
    total = len(items)

    return TaxCalendarGroupItemsResponse(
        tax_calendar_entry_id=entry.id,
        obligation_type=entry.obligation_type.value,
        items=paginate_sequence(items, page, page_size),
        page=page,
        page_size=page_size,
        total=total,
    )


def _rows_for_entry(
    repo: TaxCalendarGroupedRepository,
    entry,
    *,
    client_search: str | None,
    client_record_id: int | None,
):
    kwargs = {"client_search": client_search, "client_record_id": client_record_id}
    if entry.obligation_type == ObligationType.VAT:
        return [("vat_work_item", *row) for row in repo.list_vat_items(entry.id, **kwargs)]
    if entry.obligation_type == ObligationType.ADVANCE_PAYMENT:
        return [("advance_payment", *row) for row in repo.list_advance_items(entry.id, **kwargs)]
    if entry.obligation_type == ObligationType.ANNUAL_REPORT:
        return [("annual_report", *row) for row in repo.list_annual_items(entry.id, **kwargs)]
    return []


def _to_item(
    *,
    source_type: str,
    entry,
    row,
    client,
    client_name: str | None,
    id_number: str | None,
    today: date,
) -> TaxCalendarGroupItem:
    effective_due_date = _row_due_date(entry.obligation_type, row, entry.due_date)
    done = _is_done(entry.obligation_type, row)
    return TaxCalendarGroupItem(
        source_type=source_type,
        source_id=row.id,
        client_record_id=row.client_record_id,
        office_client_number=client.office_client_number,
        client_name=client_name,
        id_number=id_number,
        period=getattr(row, "period", None),
        period_months_count=getattr(row, "period_months_count", None),
        tax_year=getattr(row, "tax_year", None),
        status=_status_value(row.status),
        regulatory_due_date=entry.due_date,
        effective_due_date=effective_due_date,
        done=done,
        overdue=not done and effective_due_date < today,
    )


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)
