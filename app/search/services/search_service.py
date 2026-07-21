from collections.abc import Callable

from sqlalchemy.orm import Session

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.clients.client_enums import ClientStatus
from app.common.entity_links import LinkedEntity, entity_route
from app.common.enums import EntityType
from app.core.api_types import PaginatedResponse
from app.search.repositories.search_item_repository import SearchItemRepository, SearchItemRow
from app.search.repositories.search_result_repository import SearchFilters, SearchResultRepository
from app.search.schemas.search import (
    SearchClientMatch,
    SearchItem,
    SearchItemGroup,
    SearchItemGroups,
    SearchItemType,
    SearchResponse,
)

PREVIEW_LIMIT = 5

_TITLE_BUILDERS: dict[SearchItemType, Callable[[SearchItemRow], str]] = {
    SearchItemType.BINDER: lambda row: f"קלסר {row.key}",
    SearchItemType.DOCUMENT: lambda row: row.key,
    SearchItemType.VAT_WORK_ITEM: lambda row: f'דוח מע"מ {row.key}',
    SearchItemType.ANNUAL_REPORT: lambda row: f"דוח שנתי {row.key}",
    SearchItemType.ADVANCE_PAYMENT: lambda row: f"מקדמה {row.key}",
    SearchItemType.CHARGE: lambda row: f"חיוב #{row.key}",
    SearchItemType.TASK: lambda row: row.key,
    SearchItemType.NOTIFICATION: lambda row: row.key,
}


class SearchService:
    """Resolves a typed term to a client, then serves that client's items by type."""

    def __init__(self, db: Session):
        self.item_repo = SearchItemRepository(db)
        self.result_repo = SearchResultRepository(db)
        self._readers: dict[SearchItemType, Callable[..., tuple[list[SearchItemRow], int]]] = {
            SearchItemType.BINDER: self.item_repo.search_binders,
            SearchItemType.DOCUMENT: self.item_repo.search_documents,
            SearchItemType.VAT_WORK_ITEM: self.item_repo.search_vat,
            SearchItemType.ANNUAL_REPORT: self.item_repo.search_annual_reports,
            SearchItemType.ADVANCE_PAYMENT: self.item_repo.search_advance_payments,
            SearchItemType.CHARGE: self.item_repo.search_charges,
            SearchItemType.TASK: self.item_repo.search_tasks,
            SearchItemType.NOTIFICATION: self.item_repo.search_notifications,
        }

    @staticmethod
    def _item(row: SearchItemRow, result_type: SearchItemType) -> SearchItem:
        return SearchItem(
            result_type=result_type,
            id=row.id,
            title=_TITLE_BUILDERS[result_type](row),
            detail=row.detail,
            status=row.status,
            amount=row.amount,
            occurred_on=row.occurred_on,
            href=entity_route(
                LinkedEntity(result_type.value), row.id, client_record_id=row.client_record_id
            ),
        )

    def _group(self, result_type: SearchItemType, client_record_id: int) -> SearchItemGroup:
        rows, total = self._readers[result_type](client_record_id, limit=PREVIEW_LIMIT)
        return SearchItemGroup(items=[self._item(row, result_type) for row in rows], total=total)

    def _resolved_client_id(self, filters: SearchFilters, clients: list, total: int) -> int | None:
        """The client whose items are shown — only ever one client resolution returned.

        A requested `client_record_id` also narrows resolution, so a total of exactly one
        means the requested client survived every other filter. Any other total means the
        request named a client the current filters exclude, and no feed belongs to it: a
        stale selection carried in the URL must not outrank the filters beside it.

        Without a request, a term resolving to exactly one client selects it, so the common
        case — typing a name or a binder number — lands straight on that client's items
        without a second click.
        """
        if total != 1:
            return None
        if filters.client_record_id is not None:
            return filters.client_record_id
        return clients[0].id if clients else None

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
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
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
        rows, total = self.result_repo.search_clients(filters, page, page_size)
        binder_matches = self.result_repo.matched_binder_numbers([row.id for row in rows], search)
        clients = PaginatedResponse[SearchClientMatch](
            items=[
                SearchClientMatch(
                    id=row.id,
                    office_client_number=row.office_client_number,
                    name=row.name,
                    id_number=row.id_number,
                    status=row.status.value,
                    matched_binder_numbers=binder_matches.get(row.id, []),
                    href=entity_route(LinkedEntity.CLIENT, row.id),
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

        resolved_client_id = self._resolved_client_id(filters, rows, total)
        if resolved_client_id is None:
            return SearchResponse(clients=clients)

        return SearchResponse(
            clients=clients,
            items=SearchItemGroups(
                binders=self._group(SearchItemType.BINDER, resolved_client_id),
                documents=self._group(SearchItemType.DOCUMENT, resolved_client_id),
                vat_work_items=self._group(SearchItemType.VAT_WORK_ITEM, resolved_client_id),
                annual_reports=self._group(SearchItemType.ANNUAL_REPORT, resolved_client_id),
                advance_payments=self._group(SearchItemType.ADVANCE_PAYMENT, resolved_client_id),
                charges=self._group(SearchItemType.CHARGE, resolved_client_id),
                tasks=self._group(SearchItemType.TASK, resolved_client_id),
                notifications=self._group(SearchItemType.NOTIFICATION, resolved_client_id),
            ),
        )

    def list_items(
        self,
        client_record_id: int,
        result_type: SearchItemType,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[SearchItem]:
        """One type in full, for when a preview group is expanded."""
        rows, total = self._readers[result_type](
            client_record_id, limit=page_size, offset=(page - 1) * page_size
        )
        return PaginatedResponse[SearchItem](
            items=[self._item(row, result_type) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )
