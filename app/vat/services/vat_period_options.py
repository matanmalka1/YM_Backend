"""Period options logic for VAT work item creation UI."""

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import VatType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.utils.time_utils import israel_today
from app.vat.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)
from app.vat.vat_messages import VAT_CLIENT_EXEMPT, VAT_CLIENT_NOT_FOUND
from app.vat.services.vat_type_resolver import resolve_effective_vat_type


def _period_label(period_type: VatType, year: int, month: int) -> str:
    if period_type == VatType.BIMONTHLY:
        return f"{year}-{month:02d}/{year}-{month + 1:02d}"
    return f"{year}-{month:02d}"


def get_period_options(
    work_item_repo: VatWorkItemRepository,
    db,
    *,
    client_record_id: int,
    year: int | None = None,
    period_type_override: VatType | None = None,
):
    """Return period options for UI selection based on client VAT frequency."""
    client_record = ClientRecordRepository(db).get_by_id(client_record_id)
    if not client_record:
        raise NotFoundError(
            VAT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
            ErrorCode.VAT_NOT_FOUND,
        )
    legal_entity = LegalEntityRepository(db).get_by_id(client_record.legal_entity_id)
    if not legal_entity:
        raise NotFoundError(
            VAT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
            ErrorCode.VAT_NOT_FOUND,
        )

    selected_year = year or israel_today().year

    period_type = period_type_override or resolve_effective_vat_type(legal_entity)
    if period_type == VatType.EXEMPT:
        raise AppError(
            VAT_CLIENT_EXEMPT,
            ErrorCode.VAT_CLIENT_EXEMPT,
        )

    start_months = range(1, 12, 2) if period_type == VatType.BIMONTHLY else range(1, 13)
    year_prefix = f"{selected_year}-"
    opened_periods = {
        i.period
        for i in work_item_repo.list_by_client_record(client_record_id)
        if i.period.startswith(year_prefix)
    }
    options = []
    for month in start_months:
        period = f"{selected_year}-{month:02d}"
        options.append(
            {
                "period": period,
                "label": _period_label(period_type, selected_year, month),
                "start_month": month,
                "end_month": month + 1 if period_type == VatType.BIMONTHLY else month,
                "is_opened": period in opened_periods,
            }
        )

    return {
        "client_record_id": client_record_id,
        "year": selected_year,
        "period_type": period_type,
        "options": options,
    }
