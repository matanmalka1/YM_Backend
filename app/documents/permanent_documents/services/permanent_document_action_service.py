from sqlalchemy.orm import Session

from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.documents.permanent_documents.repositories.permanent_document_query_repository import (
    PermanentDocumentQueryRepository,
)


class PermanentDocumentActionService:
    def __init__(self, db: Session):
        self.db = db
        self.query_repo = PermanentDocumentQueryRepository(db)
        self.client_repo = ClientRecordRepository(db)

    def get_document_versions(
        self, client_record_id: int, document_type: str, tax_year: int | None = None
    ) -> tuple[list[PermanentDocument], bool]:
        record = self.client_repo.get_by_id(client_record_id)
        if not record:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה",
                ErrorCode.CLIENT_RECORD_NOT_FOUND,
            )
        return self.query_repo.get_all_versions_by_client_record(
            record.id, document_type, tax_year=tax_year
        )

    def list_by_annual_report(self, annual_report_id: int) -> list[PermanentDocument]:
        return self.query_repo.list_by_annual_report(annual_report_id)
