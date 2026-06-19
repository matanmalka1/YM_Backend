from sqlalchemy.orm import Session

from app.clients.repositories.client_record_read_repository import get_full_records_bulk
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.documents.permanent_documents.schemas.permanent_document import PermanentDocumentResponse


class PermanentDocumentResponseBuilder:
    def __init__(self, db: Session):
        self.db = db

    def build_one(self, document: PermanentDocument) -> PermanentDocumentResponse:
        return self.build_many([document])[0]

    def build_many(self, documents: list[PermanentDocument]) -> list[PermanentDocumentResponse]:
        client_ids = sorted({doc.client_record_id for doc in documents})
        clients = get_full_records_bulk(self.db, client_ids)
        responses: list[PermanentDocumentResponse] = []
        for doc in documents:
            response = PermanentDocumentResponse.model_validate(doc)
            client = clients.get(doc.client_record_id)
            response.client_name = client["full_name"] if client else None
            responses.append(response)
        return responses
