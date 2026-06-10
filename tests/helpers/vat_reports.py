from unittest.mock import MagicMock

from app.vat.models.vat_enums import VatWorkItemStatus


def make_item(
    id: int = 1,
    business_id: int = 10,
    period: str = "2026-01",
    status: VatWorkItemStatus = VatWorkItemStatus.MATERIAL_RECEIVED,
    net_vat: float = 0,
):
    item = MagicMock()
    item.id = id
    item.business_id = business_id
    item.client_record_id = business_id
    item.period = period
    item.status = status
    item.net_vat = net_vat
    return item
