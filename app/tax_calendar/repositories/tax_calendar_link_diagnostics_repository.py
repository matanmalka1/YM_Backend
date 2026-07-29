from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.common.obligation_chain import select_obligations
from app.vat.models.vat_work_item import VatWorkItem


class TaxCalendarLinkDiagnosticsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def null_link_ids(self, model) -> list[int]:
        """Rows of ``model`` with no calendar link — a data defect, per chain link.

        Superseded rows are included deliberately. This is an integrity check,
        not a business list: a corrected row with a missing regulatory link is
        just as broken as the tip, and hiding it would make the defect count
        shrink every time someone files an amendment.
        """
        return list(
            self.db.scalars(
                select_obligations(model, model.id, include_superseded=True).where(
                    model.tax_calendar_entry_id.is_(None)
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
