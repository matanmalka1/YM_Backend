from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_read_repository import get_full_records_bulk
from app.search.repositories.search_result_repository import SearchResultRepository
from app.search.schemas.search import DocumentSearchResult

_DOCUMENT_SEARCH_LIMIT = 50


class DocumentSearchService:
    """Searches permanent documents by filename or type."""

    def __init__(self, db: Session):
        self.db = db
        self.search_repo = SearchResultRepository(db)
        self.business_repo = BusinessRepository(db)

    def search_documents(
        self,
        query: str | None,
        filename: str | None,
        client_scope: Select[tuple[int]],
    ) -> list[DocumentSearchResult]:
        docs = self.search_repo.search_documents(
            query=query,
            filename=filename,
            client_scope=client_scope,
            limit=_DOCUMENT_SEARCH_LIMIT,
        )
        businesses = self.business_repo.list_by_ids(
            list({doc.business_id for doc in docs if doc.business_id is not None})
        )
        business_cache = {business.id: business.full_name for business in businesses}
        client_map = get_full_records_bulk(self.db, [doc.client_record_id for doc in docs])
        results = []
        for doc in docs:
            client = client_map.get(doc.client_record_id)
            results.append(
                DocumentSearchResult(
                    id=doc.id,
                    client_record_id=doc.client_record_id,
                    office_client_number=client["office_client_number"] if client else None,
                    client_name=client["full_name"] if client else "לא ידוע",
                    business_id=doc.business_id,
                    business_name=business_cache.get(doc.business_id),
                    document_type=doc.document_type,
                    original_filename=doc.original_filename,
                    tax_year=doc.tax_year,
                )
            )
        return results
