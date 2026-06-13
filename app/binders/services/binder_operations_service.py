from datetime import date

from sqlalchemy.orm import Session

from app.binders.models.binder import Binder
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_list_service import BinderListService
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import NotFoundError


class BinderOperationsService:
    """Operational binder queries."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = BinderRepository(db)
        self.list_service = BinderListService(db)

    def get_open_binders(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        client_record_id: int | None = None,
        binder_number: str | None = None,
        location_status: str | None = None,
        capacity_status: str | None = None,
        created_after: date | None = None,
        created_before: date | None = None,
    ) -> tuple[list[Binder], int]:
        """Get open binders with optional filters and pagination."""
        filters = {
            "client_record_id": client_record_id,
            "binder_number": binder_number,
            "location_status": location_status,
            "capacity_status": capacity_status,
            "created_after": created_after,
            "created_before": created_before,
        }
        items = self.repo.list_open_binders(page=page, page_size=page_size, **filters)
        total = self.repo.count_open_binders(**filters)
        return items, total

    def get_client_binders(
        self,
        client_record_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Binder], int]:
        """Get all binders for a client with pagination."""
        client_record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if not client_record:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה", "CLIENT_RECORD.NOT_FOUND"
            )
        binders = self.repo.list_by_client_record_paginated(
            client_record_id,
            page=page,
            page_size=page_size,
        )
        total = self.repo.count_by_client_record(client_record_id)
        return binders, total

    def get_active_binder_for_client(self, client_record_id: int) -> Binder | None:
        """Return the intake-eligible binder for a client, or None."""
        client_record = ClientRecordRepository(self.db).get_by_id(client_record_id)
        if not client_record:
            return None
        return self.repo.get_active_by_client_record(client_record_id)

    def map_active_binders_for_clients(self, client_record_ids: list[int]) -> dict[int, Binder]:
        """Return {client_record_id: binder} for each client's intake-eligible binder."""
        return self.repo.map_active_by_clients(client_record_ids)

    def enrich_binder(
        self,
        binder: Binder,
        reference_date: date | None = None,
    ) -> dict:
        """
        Enrich binder with operational state.

        Returns a dict that matches BinderDetailResponse fields:
          id, client_record_id, office_client_number, client_name, client_id_number, binder_number, period_start, period_end,
          lifecycle fields and days_in_office.
        """
        response = self.list_service.build_binder_response(binder, reference_date=reference_date)
        return response.model_dump()
