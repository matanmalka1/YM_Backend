from sqlalchemy.orm import Session

from app.binders.services.binder_operations_service import BinderOperationsService
from app.clients.schemas.client_record_response import (
    AnnualTurnover,
    ClientRecordResponse,
)
from app.utils.time_utils import utcnow
from app.vat.repositories.vat_client_summary_repository import (
    VatClientSummaryRepository,
)


class ClientEnrichmentService:
    def __init__(self, db: Session):
        self._binder_service = BinderOperationsService(db)
        self._vat_repo = VatClientSummaryRepository(db)

    def _compute_annual_turnover(self, client: ClientRecordResponse, year: int) -> AnnualTurnover:
        reported = self._vat_repo.get_annual_turnover(client.id, year)
        if reported is not None:
            return AnnualTurnover(amount=reported, source="reported", year=year)
        if client.annual_revenue is not None:
            return AnnualTurnover(amount=client.annual_revenue, source="manual", year=year)
        return AnnualTurnover(amount=None, source="none", year=year)

    def enrich_single(
        self, response: ClientRecordResponse, tax_year: int | None = None
    ) -> ClientRecordResponse:
        active = self._binder_service.get_active_binder_for_client(response.id)
        if active:
            response.active_binder_number = active.binder_number
        year = tax_year or utcnow().year
        response.annual_turnover = self._compute_annual_turnover(response, year)
        return response

    def enrich_list_binders(
        self, items: list[ClientRecordResponse]
    ) -> list[ClientRecordResponse]:
        """Set ``active_binder_number`` for a page of clients.

        The clients list uses a thin DTO and intentionally does not expose annual
        turnover, so this path skips VAT turnover lookups.
        """
        if not items:
            return items
        client_ids = [c.id for c in items]
        active_binders = self._binder_service.map_active_binders_for_clients(client_ids)
        for client in items:
            if client.id in active_binders:
                client.active_binder_number = active_binders[client.id].binder_number
        return items