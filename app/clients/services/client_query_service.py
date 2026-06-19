from sqlalchemy.orm import Session

from app.clients.client_enums import ClientStatus
from app.clients.repositories.client_record_read_repository import (
    get_full_record,
    get_full_record_including_deleted,
    get_full_records_bulk,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.schemas.client_conflicts import (
    ActiveClientSummary,
    ClientConflictInfo,
    DeletedClientSummary,
)
from app.clients.schemas.client_record_response import (
    ClientRecordListItem,
    ClientRecordListResponse,
    ClientRecordListStats,
    ClientRecordResponse,
    ClientSidebarItemResponse,
    ClientSidebarListResponse,
)
from app.clients.services.client_enrichment_service import ClientEnrichmentService
from app.common.enums import EntityType
from app.core.api_types import SortOrder
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class ClientQueryService:
    def __init__(self, db: Session):
        self.db = db
        self.record_repo = ClientRecordRepository(db)

    def get_client_stats(self) -> ClientRecordListStats:
        counts = self.record_repo.count_by_status()
        return ClientRecordListStats(
            active=counts.get(ClientStatus.ACTIVE, 0),
            frozen=counts.get(ClientStatus.FROZEN, 0),
            closed=counts.get(ClientStatus.CLOSED, 0),
        )

    def list_all_clients(self) -> list[ClientRecordResponse]:
        records = self.record_repo.list_all()
        full_map = get_full_records_bulk(self.db, [r.id for r in records])
        return [ClientRecordResponse(**full_map[r.id]) for r in records if r.id in full_map]

    def get_conflict_info(self, id_number: str) -> ClientConflictInfo:
        active_records = self.record_repo.get_active_by_id_number(id_number)
        deleted_records = self.record_repo.get_deleted_by_id_number(id_number)
        active_full = get_full_records_bulk(self.db, [r.id for r in active_records])
        deleted_full = {
            r.id: get_full_record_including_deleted(self.db, r.id) for r in deleted_records
        }
        return ClientConflictInfo(
            id_number=id_number,
            active_clients=[
                ActiveClientSummary(**active_full[r.id])
                for r in active_records
                if r.id in active_full
            ],
            deleted_clients=[
                DeletedClientSummary(**deleted_full[r.id])
                for r in deleted_records
                if deleted_full.get(r.id)
            ],
        )

    def get_full_client(
        self, client_record_id: int, tax_year: int | None = None
    ) -> ClientRecordResponse:
        data = get_full_record(self.db, client_record_id)
        if not data:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה", ErrorCode.CLIENT_RECORD_NOT_FOUND
            )
        return ClientEnrichmentService(self.db).enrich_single(
            ClientRecordResponse(**data), tax_year=tax_year
        )

    def get_full_client_including_deleted(self, client_record_id: int) -> ClientRecordResponse:
        data = get_full_record_including_deleted(self.db, client_record_id)
        if not data:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה", ErrorCode.CLIENT_RECORD_NOT_FOUND
            )
        return ClientRecordResponse(**data)

    def list_full_clients(
        self,
        search: str | None = None,
        status: ClientStatus | None = None,
        accountant_id: int | None = None,
        entity_type: EntityType | None = None,
        sort_by: str = "full_name",
        order: SortOrder = SortOrder.asc,
        page: int = 1,
        page_size: int = 20,
    ) -> ClientRecordListResponse:
        records = self.record_repo.list(
            search=search,
            status=status,
            accountant_id=accountant_id,
            entity_type=entity_type,
            sort_by="official_name" if sort_by == "full_name" else sort_by,
            order=order,
            page=page,
            page_size=page_size,
        )
        total = self.record_repo.count(
            search=search,
            status=status,
            accountant_id=accountant_id,
            entity_type=entity_type,
        )
        record_ids = [r.id for r in records]
        full_map = get_full_records_bulk(self.db, record_ids)
        full_items = [
            ClientRecordResponse(**full_map[rid]) for rid in record_ids if rid in full_map
        ]
        full_items = ClientEnrichmentService(self.db).enrich_list_binders(full_items)
        items = [ClientRecordListItem.model_validate(item) for item in full_items]
        counts = self.record_repo.count_by_status(
            search=search,
            accountant_id=accountant_id,
            entity_type=entity_type,
        )
        stats = ClientRecordListStats(
            active=counts.get(ClientStatus.ACTIVE, 0),
            frozen=counts.get(ClientStatus.FROZEN, 0),
            closed=counts.get(ClientStatus.CLOSED, 0),
        )
        return ClientRecordListResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            stats=stats,
        )

    def list_sidebar_clients(
        self,
        search: str | None = None,
        sort_by: str = "full_name",
        order: SortOrder = SortOrder.asc,
        page: int = 1,
        page_size: int = 100,
    ) -> ClientSidebarListResponse:
        rows = self.record_repo.list_sidebar(
            search=search,
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
        )
        total = self.record_repo.count_sidebar(search=search)
        return ClientSidebarListResponse(
            items=[ClientSidebarItemResponse(**dict(row)) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )
