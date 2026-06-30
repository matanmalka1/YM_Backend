from datetime import date

from sqlalchemy.orm import Session

from app.binders.models.binder import Binder
from app.binders.models.binder_intake import BinderIntake
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_intake_service import BinderIntakeService


class BinderService:
    """Binder orchestration that is not lifecycle transition logic."""

    def __init__(self, db: Session):
        self.db = db
        self.binder_repo = BinderRepository(db)
        self.intake_service = BinderIntakeService(db)

    def receive_binder(
        self,
        client_record_id: int,
        received_at: date,
        received_by: int,
        open_new_binder: bool = False,
        notes: str | None = None,
        materials: list[dict] | None = None,
        actor_display_name: str | None = None,
    ) -> tuple[Binder, BinderIntake, bool]:
        return self.intake_service.receive(
            client_record_id=client_record_id,
            open_new_binder=open_new_binder,
            received_at=received_at,
            received_by=received_by,
            notes=notes,
            materials=materials,
            actor_display_name=actor_display_name,
        )

    def delete_binder(self, binder_id: int, actor_id: int) -> bool:
        binder = self.binder_repo.get_by_id(binder_id)
        if not binder:
            return False
        return self.binder_repo.soft_delete(binder_id, deleted_by=actor_id)
