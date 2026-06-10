from app.common.enums import VatType
from app.vat.models.vat_work_item import VatWorkItem


def apply_vat_work_item_filters(
    query,
    *,
    period: str | None = None,
    client_record_ids: list[int] | None = None,
    period_type: VatType | None = None,
):
    if period:
        query = query.where(VatWorkItem.period == period)
    if client_record_ids is not None:
        query = query.where(VatWorkItem.client_record_id.in_(client_record_ids))
    if period_type is not None:
        query = query.where(VatWorkItem.period_type == period_type)
    return query
