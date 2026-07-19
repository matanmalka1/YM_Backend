from dataclasses import asdict

from sqlalchemy.orm import Session

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus
from app.common.enums import EntityType
from app.search.repositories.search_item_repository import SearchItemRepository, SearchItemRow
from app.search.repositories.search_result_repository import SearchFilters, SearchResultRepository
from app.search.schemas.search import (
    DocumentSearchResult,
    OperationalSearchGroup,
    OperationalSearchItem,
    OperationalSearchResults,
)
from app.search.services.search_document_search_service import DocumentSearchService


class SearchService:
    """Unified search for clients and binders."""

    def __init__(self, db: Session):
        self.db = db
        self.item_repo = SearchItemRepository(db)
        self.result_repo = SearchResultRepository(db)

    @staticmethod
    def _item(row: SearchItemRow, result_type: str) -> OperationalSearchItem:
        titles = {
            "task": row.key,
            "vat_work_item": f'דוח מע"מ {row.key}',
            "annual_report": f"דוח שנתי {row.key}",
            "charge": f"חיוב #{row.id}",
            "advance_payment": f"מקדמה {row.key}",
        }
        hrefs = {
            "task": f"/tasks?task_id={row.id}",
            "vat_work_item": f"/tax/vat/{row.id}",
            "annual_report": f"/clients/{row.client_record_id}/annual-reports/{row.id}",
            "charge": f"/charges?charge_id={row.id}",
            "advance_payment": (
                f"/clients/{row.client_record_id}/advance-payments?advance_payment_id={row.id}"
            ),
        }
        return OperationalSearchItem(
            result_type=result_type,
            id=row.id,
            client_record_id=row.client_record_id,
            office_client_number=row.office_client_number,
            client_name=row.client_name,
            title=titles[result_type],
            detail=row.detail,
            status=row.status,
            amount=row.amount,
            href=hrefs[result_type],
        )

    def search_operational_items(
        self,
        search: str | None,
        client_record_id: int | None,
        *,
        id_number: str | None = None,
        client_status: ClientStatus | None = None,
        entity_type: EntityType | None = None,
        binder_number: str | None = None,
        binder_location_status: BinderLocationStatus | None = None,
        binder_capacity_status: BinderCapacityStatus | None = None,
    ) -> OperationalSearchResults:
        term = search.strip().lower() if search else ""
        if not term and client_record_id is None:
            return OperationalSearchResults()

        scope = self.result_repo.matching_client_ids(
            SearchFilters(
                client_record_id=client_record_id,
                id_number=id_number,
                client_status=client_status,
                entity_type=entity_type,
                binder_number=binder_number,
                binder_location_status=binder_location_status,
                binder_capacity_status=binder_capacity_status,
            )
        )

        def group(rows_and_total, result_type: str) -> OperationalSearchGroup:
            rows, total = rows_and_total
            return OperationalSearchGroup(
                items=[self._item(row, result_type) for row in rows], total=total
            )

        return OperationalSearchResults(
            tasks=group(self.item_repo.search_tasks(term or None, scope), "task"),
            vat_work_items=group(self.item_repo.search_vat(term or None, scope), "vat_work_item"),
            annual_reports=group(
                self.item_repo.search_annual_reports(term or None, scope), "annual_report"
            ),
            charges=group(self.item_repo.search_charges(term or None, scope), "charge"),
            advance_payments=group(
                self.item_repo.search_advance_payments(term or None, scope), "advance_payment"
            ),
        )

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
        filters = SearchFilters(
            search=search,
            client_record_id=client_record_id,
            id_number=id_number,
            client_status=client_status,
            entity_type=entity_type,
            binder_number=binder_number,
            binder_location_status=binder_location_status,
            binder_capacity_status=binder_capacity_status,
        )
        client_scope = self.result_repo.matching_client_ids(filters)
        documents = (
            DocumentSearchService(self.db).search_documents(search, filename, client_scope)
            if search or filename
            else []
        )
        has_primary_filter = bool(
            search
            or client_record_id
            or id_number
            or client_status
            or entity_type
            or binder_number
            or binder_location_status
            or binder_capacity_status
        )
        if not has_primary_filter:
            return [], 0, documents

        rows, total = self.result_repo.search_primary(filters, page, page_size)
        return [asdict(row) for row in rows], total, documents
