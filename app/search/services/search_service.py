from collections.abc import Callable

from sqlalchemy.orm import Session

from app.common.entity_links import LinkedEntity, entity_route
from app.core.api_types import PaginatedResponse
from app.notifications.models.notification import TRIGGER_LABELS, NotificationTrigger
from app.search.repositories.search_match_repository import (
    SearchMatchRepository,
    SearchMatchRow,
)
from app.search.repositories.search_result_repository import SearchResultRepository
from app.search.schemas.search import (
    SearchClientMatch,
    SearchMatch,
    SearchMatchGroup,
    SearchMatchGroups,
    SearchMatchType,
    SearchResponse,
)
from app.search.search_term_parser import parse_search_term

PREVIEW_LIMIT = 5

_TITLE_BUILDERS: dict[SearchMatchType, Callable[[SearchMatchRow], str]] = {
    SearchMatchType.BINDER: lambda row: f"קלסר {row.key}",
    SearchMatchType.DOCUMENT: lambda row: row.key,
    SearchMatchType.VAT_WORK_ITEM: lambda row: f'דוח מע"מ {row.key}',
    SearchMatchType.ANNUAL_REPORT: lambda row: f"דוח שנתי {row.key}",
    SearchMatchType.ADVANCE_PAYMENT: lambda row: f"מקדמה {row.key}",
    SearchMatchType.CHARGE: lambda row: f"חיוב #{row.key}",
    SearchMatchType.TASK: lambda row: row.key,
    SearchMatchType.NOTIFICATION: lambda row: TRIGGER_LABELS[NotificationTrigger(row.key)],
}

_GROUP_FIELDS: dict[SearchMatchType, str] = {
    SearchMatchType.BINDER: "binders",
    SearchMatchType.DOCUMENT: "documents",
    SearchMatchType.VAT_WORK_ITEM: "vat_work_items",
    SearchMatchType.ANNUAL_REPORT: "annual_reports",
    SearchMatchType.ADVANCE_PAYMENT: "advance_payments",
    SearchMatchType.CHARGE: "charges",
    SearchMatchType.TASK: "tasks",
    SearchMatchType.NOTIFICATION: "notifications",
}


class SearchService:
    """Resolves the typed term to clients and to matching records, side by side."""

    def __init__(self, db: Session):
        self.match_repo = SearchMatchRepository(db)
        self.result_repo = SearchResultRepository(db)

    @staticmethod
    def _match(row: SearchMatchRow) -> SearchMatch:
        return SearchMatch(
            result_type=row.result_type,
            id=row.id,
            title=_TITLE_BUILDERS[row.result_type](row),
            detail=row.detail,
            status=row.status,
            amount=row.amount,
            occurred_on=row.occurred_on,
            href=entity_route(
                LinkedEntity(row.result_type.value), row.id, client_record_id=row.client_record_id
            ),
            client_record_id=row.client_record_id,
            client_name=row.client_name,
            client_office_number=row.client_office_number,
        )

    def search(self, search: str, page: int = 1, page_size: int = 20) -> SearchResponse:
        rows, total = self.result_repo.search_clients(search, page, page_size)
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

        match_rows, totals = self.match_repo.search_matches(
            parse_search_term(search), PREVIEW_LIMIT
        )
        groups: dict[str, SearchMatchGroup] = {}
        for row in match_rows:
            group = groups.setdefault(
                _GROUP_FIELDS[row.result_type],
                SearchMatchGroup(total=totals.get(row.result_type, 0)),
            )
            group.items.append(self._match(row))

        return SearchResponse(clients=clients, matches=SearchMatchGroups(**groups))

    def list_matches(
        self,
        search: str,
        result_type: SearchMatchType,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[SearchMatch]:
        """One type's matches in full, for when a preview group is expanded."""
        rows, total = self.match_repo.list_matches(
            parse_search_term(search), result_type, page, page_size
        )
        return PaginatedResponse[SearchMatch](
            items=[self._match(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )
