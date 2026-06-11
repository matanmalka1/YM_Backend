from datetime import date

from sqlalchemy.orm import Session

from app.utils.time_utils import israel_today


class SignalsService:
    """
    Compute operational signals for UX.

    Signals are:
    - Derived dynamically (NOT persisted)
    - Advisory only (non-blocking)
    - Internal UX indicators
    """

    def __init__(self, db: Session):
        self.db = db
        from app.documents.permanent_documents.services.permanent_document_service import (
            PermanentDocumentService,
        )

        self.document_service = PermanentDocumentService(db)

    def compute_business_operational_signals(
        self,
        business_id: int,
        reference_date: date | None = None,
    ) -> dict:
        if reference_date is None:
            reference_date = israel_today()
        missing_docs = self.document_service.get_missing_document_types(business_id)
        return {
            "business_id": business_id,
            "missing_documents": list(missing_docs),
        }
