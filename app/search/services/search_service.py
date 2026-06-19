from sqlalchemy.orm import Session

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.client_enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import EntityType
from app.core.pagination import paginate_sequence
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.search.schemas.search import DocumentSearchResult
from app.search.services.search_document_search_service import DocumentSearchService

# Safety ceiling for mixed searches that must be resolved in memory.
# Pure client-only searches already use DB-level pagination and are not affected.
# Known architectural debt — see CLAUDE.md.
_MIXED_SEARCH_BINDER_LIMIT = 1000
_MIXED_SEARCH_CLIENT_LIMIT = 500


class SearchService:
    """Unified search for clients and binders."""

    def __init__(self, db: Session):
        self.db = db
        self.client_record_repo = ClientRecordRepository(db)
        self.legal_entity_repo = LegalEntityRepository(db)
        self.business_repo = BusinessRepository(db)
        self.binder_repo = BinderRepository(db)

    def _legal_entity_map(self, legal_entity_ids: list[int]) -> dict[int, LegalEntity]:
        entities = self.legal_entity_repo.list_by_ids(list(set(legal_entity_ids)))
        return {entity.id: entity for entity in entities}

    def search(
        self,
        search: str | None = None,
        client_record_id: int | None = None,
        id_number: str | None = None,
        binder_number: str | None = None,
        client_status: ClientStatus | None = None,
        entity_type: EntityType | None = None,
        binder_location_status: BinderLocationStatus | None = None,
        binder_capacity_status: BinderCapacityStatus | None = None,
        filename: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int, list[DocumentSearchResult]]:
        doc_service = DocumentSearchService(self.db)
        document_query = search or filename
        if client_record_id is not None and document_query:
            documents = doc_service.list_client_documents(client_record_id, document_query)
        elif search or filename:
            documents = doc_service.search_documents(search or "", filename=filename)
        else:
            documents = []

        has_client_filter = bool(
            search or client_record_id or id_number or client_status or entity_type
        )
        has_binder_filter = bool(
            search
            or client_record_id
            or binder_number
            or binder_location_status
            or binder_capacity_status
        )

        # --- Pure client-only search: DB-level pagination ---
        if has_client_filter and not has_binder_filter:
            records, total = self.client_record_repo.search(
                search=search,
                client_id=client_record_id,
                id_number=id_number,
                status=client_status,
                entity_type=entity_type,
                page=page,
                page_size=page_size,
            )
            legal_map = self._legal_entity_map([record.legal_entity_id for record in records])
            binder_map = self.binder_repo.map_active_by_clients([record.id for record in records])
            return (
                [
                    {
                        "result_type": "client",
                        "client_record_id": record.id,
                        "office_client_number": record.office_client_number,
                        "client_name": legal_map[record.legal_entity_id].official_name
                        if legal_map.get(record.legal_entity_id)
                        else "לא ידוע",
                        "id_number": legal_map[record.legal_entity_id].id_number
                        if legal_map.get(record.legal_entity_id)
                        else None,
                        "client_status": record.status,
                        "binder_id": binder_map[record.id].id if record.id in binder_map else None,
                        "binder_number": binder_map[record.id].binder_number
                        if record.id in binder_map
                        else None,
                    }
                    for record in records
                ],
                total,
                documents,
            )

        # --- Mixed / binder-number search: build full result set then paginate ---
        # Bounded by _MIXED_SEARCH_*_LIMIT. Results beyond ceiling are excluded.
        results: list[dict] = []

        if has_client_filter:
            all_records, _ = self.client_record_repo.search(
                search=search,
                client_id=client_record_id,
                id_number=id_number,
                status=client_status,
                entity_type=entity_type,
                page=1,
                page_size=_MIXED_SEARCH_CLIENT_LIMIT,
            )
            legal_map = self._legal_entity_map([record.legal_entity_id for record in all_records])
            client_binder_map = self.binder_repo.map_active_by_clients(
                [record.id for record in all_records]
            )
            for record in all_records:
                b = client_binder_map.get(record.id)
                legal_entity = legal_map.get(record.legal_entity_id)
                results.append(
                    {
                        "result_type": "client",
                        "client_record_id": record.id,
                        "office_client_number": record.office_client_number,
                        "client_name": legal_entity.official_name if legal_entity else "לא ידוע",
                        "id_number": legal_entity.id_number if legal_entity else None,
                        "client_status": record.status,
                        "binder_id": b.id if b else None,
                        "binder_number": b.binder_number if b else None,
                    }
                )

        if has_binder_filter:
            db_binder_number = binder_number or (
                search if not (client_record_id or id_number) else None
            )
            include_handed_over = binder_location_status == BinderLocationStatus.HANDED_OVER
            binders = self.binder_repo.list_active(
                binder_number=db_binder_number,
                location_status=binder_location_status.value if binder_location_status else None,
                capacity_status=binder_capacity_status.value if binder_capacity_status else None,
                page=1,
                page_size=_MIXED_SEARCH_BINDER_LIMIT,
                include_handed_over=include_handed_over,
            )
            if client_record_id is not None:
                binders = [
                    binder for binder in binders if binder.client_record_id == client_record_id
                ]
            binder_cr_ids = [b.client_record_id for b in binders]
            records = {
                record.id: record for record in self.client_record_repo.list_by_ids(binder_cr_ids)
            }
            cr_to_legal = {record.id: record.legal_entity_id for record in records.values()}
            legal_entity_ids = list(cr_to_legal.values())
            legal_map = self._legal_entity_map(legal_entity_ids)
            businesses = self.business_repo.list_by_legal_entity_ids(legal_entity_ids)
            legal_to_business = {b.legal_entity_id: b for b in businesses}
            for binder in binders:
                record = records.get(binder.client_record_id)
                legal_id = cr_to_legal.get(binder.client_record_id)
                business = legal_to_business.get(legal_id) if legal_id else None
                legal_entity = legal_map.get(legal_id) if legal_id else None
                results.append(
                    {
                        "result_type": "binder",
                        "client_record_id": binder.client_record_id,
                        "office_client_number": record.office_client_number if record else None,
                        "client_name": business.full_name
                        if business
                        else (legal_entity.official_name if legal_entity else "לא ידוע"),
                        "id_number": legal_entity.id_number if legal_entity else None,
                        "client_status": record.status if record else None,
                        "binder_id": binder.id,
                        "binder_number": binder.binder_number,
                    }
                )

        total = len(results)
        return paginate_sequence(results, page, page_size), total, documents
