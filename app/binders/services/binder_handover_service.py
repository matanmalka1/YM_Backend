from datetime import date

from sqlalchemy.orm import Session

from app.binders.binder_messages import BINDER_HANDOVER_INVALID_BINDERS
from app.binders.models.binder import Binder, BinderLocationStatus
from app.binders.models.binder_handover import BinderHandover
from app.binders.repositories.binder_handover_repository import BinderHandoverRepository
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError


class BinderHandoverService:
    """Grouped binder handover: hand over multiple binders to a client in one event."""

    def __init__(self, db: Session):
        self.db = db
        self.binder_repo = BinderRepository(db)
        self.lifecycle_service = BinderLifecycleService(db)
        self.handover_repo = BinderHandoverRepository(db)

    def create_handover(
        self,
        client_record_id: int,
        binder_ids: list[int],
        received_by_name: str,
        handed_over_at: date,
        until_period_year: int,
        until_period_month: int,
        actor_id: int,
        notes: str | None = None,
    ) -> BinderHandover:
        """
        Hand over multiple binders to a client in a single grouped event.

        Validates:
        - All binders belong to client_record_id
        - All binders are ready for handover

        Transitions each binder to handed_over and creates a BinderHandover record.
        """
        binders = self._load_and_validate_binders(client_record_id, binder_ids)

        for binder in binders:
            self.lifecycle_service.handover_loaded_binder(
                binder,
                changed_by_user_id=actor_id,
                handed_over_at=handed_over_at,
                handover_recipient_name=received_by_name,
                notes=notes,
            )

        handover = self.handover_repo.create(
            client_record_id=client_record_id,
            received_by_name=received_by_name,
            handed_over_at=handed_over_at,
            until_period_year=until_period_year,
            until_period_month=until_period_month,
            binder_ids=binder_ids,
            created_by=actor_id,
            notes=notes,
        )

        return handover

    def _load_and_validate_binders(
        self, client_record_id: int, binder_ids: list[int]
    ) -> list[Binder]:
        binders = []
        for bid in binder_ids:
            binder = self.binder_repo.get_by_id_for_update(bid)
            if not binder or binder.client_record_id != client_record_id:
                raise AppError(BINDER_HANDOVER_INVALID_BINDERS, ErrorCode.BINDER_HANDOVER_INVALID)
            if binder.location_status != BinderLocationStatus.READY_FOR_HANDOVER:
                raise AppError(BINDER_HANDOVER_INVALID_BINDERS, ErrorCode.BINDER_HANDOVER_INVALID)
            binders.append(binder)
        return binders
