"""Service: export VAT client data to Excel or PDF."""

from __future__ import annotations

import os
import tempfile

from sqlalchemy.orm import Session

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.repositories.legal_entity_repository import LegalEntityRepository
from app.core.exceptions import NotFoundError
from app.vat.repositories.vat_client_summary_repository import (
    VatClientSummaryRepository,
)
from app.vat.schemas.vat_client_summary_schema import VatPeriodRow
from app.vat.services.messages import VAT_CLIENT_NOT_FOUND
from app.vat.services.vat_export_excel import export_vat_to_excel
from app.vat.services.vat_export_pdf import export_vat_to_pdf
from app.vat.services.vat_report_queries import get_vat_deadline_fields


def _get_export_dir() -> str:
    path = os.path.join(tempfile.gettempdir(), "exports")
    os.makedirs(path, exist_ok=True)
    return path


def _load(db: Session, client_record_id: int, year: int):
    client_record = ClientRecordRepository(db).get_by_id(client_record_id)
    if not client_record:
        raise NotFoundError(
            VAT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
            "VAT.NOT_FOUND",
        )
    legal_entity = LegalEntityRepository(db).get_by_id(client_record.legal_entity_id)
    display_name = legal_entity.official_name if legal_entity else f"לקוח #{client_record_id}"
    all_periods = VatClientSummaryRepository(db).get_periods_for_client(client_record_id)
    periods = [
        VatPeriodRow(
            work_item_id=r.id,
            period=r.period,
            period_type=r.period_type.value if r.period_type else None,
            status=r.status,
            total_output_vat=r.total_output_vat,
            total_input_vat=r.total_input_vat,
            net_vat=r.net_vat,
            total_output_net=r.total_output_net,
            total_input_net=r.total_input_net,
            final_vat_amount=r.final_vat_amount,
            filed_at=r.filed_at,
            **get_vat_deadline_fields(r, r.submission_method),
        )
        for r, *_ in all_periods
        if r.period.startswith(str(year))
    ]
    return display_name, periods


def export_to_excel(db: Session, client_record_id: int, year: int) -> dict[str, object]:
    display_name, periods = _load(db, client_record_id, year)
    return export_vat_to_excel(display_name, client_record_id, year, periods, _get_export_dir())


def export_to_pdf(db: Session, client_record_id: int, year: int) -> dict[str, object]:
    display_name, periods = _load(db, client_record_id, year)
    return export_vat_to_pdf(display_name, client_record_id, year, periods, _get_export_dir())


_MEDIA_TYPES = {
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def export(
    db: Session, client_record_id: int, year: int, fmt: str
) -> tuple[dict[str, object], str]:
    """Dispatch export by format. Returns (result_dict, media_type)."""
    if fmt == "excel":
        result = export_to_excel(db, client_record_id, year)
    else:
        result = export_to_pdf(db, client_record_id, year)
    return result, _MEDIA_TYPES[fmt]
