from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.vat.models.vat_work_item import VatWorkItem


class TaxCalendarLinkDiagnosticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def null_link_ids(self, model) -> list[int]:
        return list(
            self.db.scalars(
                select(model.id).where(
                    model.deleted_at.is_(None),
                    model.tax_calendar_entry_id.is_(None),
                )
            ).all()
        )

    def find_null_calendar_links(self) -> dict[str, dict[str, object]]:
        def collect(model):
            ids = self.null_link_ids(model)
            return {"count": len(ids), "ids": ids}

        return {
            "vat_work_items": collect(VatWorkItem),
            "advance_payments": collect(AdvancePayment),
            "annual_reports": collect(AnnualReport),
        }
