from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder
from app.charges.models.charge import Charge
from app.common.source_types import WorkQueueSourceType
from app.vat.models.vat_work_item import VatWorkItem

_SOURCE_MODELS: dict[WorkQueueSourceType, type] = {
    WorkQueueSourceType.VAT_WORK_ITEM: VatWorkItem,
    WorkQueueSourceType.ANNUAL_REPORT: AnnualReport,
    WorkQueueSourceType.ADVANCE_PAYMENT: AdvancePayment,
    WorkQueueSourceType.CHARGE: Charge,
    WorkQueueSourceType.BINDER: Binder,
}


class TaskSourceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def exists(self, source_type: WorkQueueSourceType, source_id: int) -> bool:
        model = _SOURCE_MODELS.get(source_type)
        if model is None:
            return False
        row = self.db.scalars(select(model).where(model.id == source_id)).first()
        return row is not None and getattr(row, "deleted_at", None) is None

    def get_client_record_id(self, source_type: WorkQueueSourceType, source_id: int) -> int | None:
        model = _SOURCE_MODELS.get(source_type)
        if model is None:
            return None
        return self.db.scalar(
            select(model.client_record_id).where(  # type: ignore[attr-defined]
                model.id == source_id,
                model.deleted_at.is_(None),  # type: ignore[attr-defined]
            )
        )
