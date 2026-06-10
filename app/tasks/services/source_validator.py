from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder
from app.charges.models.charge import Charge
from app.common.source_types import WorkQueueSourceType
from app.vat_reports.models.vat_work_item import VatWorkItem


def source_exists(db: Session, source_type: WorkQueueSourceType, source_id: int) -> bool:
    """Return True iff the referenced source record exists and is not soft-deleted."""
    model_map = {
        WorkQueueSourceType.VAT_WORK_ITEM: VatWorkItem,
        WorkQueueSourceType.ANNUAL_REPORT: AnnualReport,
        WorkQueueSourceType.ADVANCE_PAYMENT: AdvancePayment,
        WorkQueueSourceType.CHARGE: Charge,
        WorkQueueSourceType.BINDER: Binder,
    }
    model = model_map.get(source_type)
    if model is None:
        return False
    row = db.scalars(select(model).where(model.id == source_id)).first()
    if row is None:
        return False
    return getattr(row, "deleted_at", None) is None
