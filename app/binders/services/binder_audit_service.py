from sqlalchemy.orm import Session

from app.binders.models.binder import Binder
from app.binders.models.binder_lifecycle_log import BinderLifecycleLog
from app.binders.repositories.binder_intake_material_repository import (
    BinderIntakeMaterialRepository,
)
from app.binders.repositories.binder_intake_repository import BinderIntakeRepository
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.repositories.binder_lifecycle_log_repository import BinderLifecycleLogRepository
from app.binders.schemas.binder import (
    BinderAuditEntry,
    BinderIntakeMaterialResponse,
    BinderIntakeResponse,
)
from app.binders.services.messages import BINDER_NOT_FOUND
from app.core.exceptions import NotFoundError
from app.users.repositories.user_repository import UserRepository


class BinderAuditService:
    """Binder audit read service."""

    def __init__(self, db: Session):
        self.db = db
        self.binder_repo = BinderRepository(db)
        self.log_repo = BinderLifecycleLogRepository(db)
        self.intake_repo = BinderIntakeRepository(db)
        self.material_repo = BinderIntakeMaterialRepository(db)
        self.user_repo = UserRepository(db)

    def build_audit_entries(self, logs: list[BinderLifecycleLog]) -> list[BinderAuditEntry]:
        """Enrich lifecycle log records with changed_by user names."""
        user_ids = {log.changed_by_user_id for log in logs}
        users = [self.user_repo.get_by_id(uid) for uid in user_ids]
        name_map = {u.id: u.full_name for u in users if u}
        return [
            BinderAuditEntry(
                field_name=log.field_name,
                old_value=log.old_value,
                new_value=log.new_value,
                changed_by_user_id=log.changed_by_user_id,
                changed_by_name=name_map.get(log.changed_by_user_id),
                changed_at=log.changed_at,
                notes=log.notes,
            )
            for log in logs
        ]

    def get_binder_audit(
        self, binder_id: int, page: int = 1, page_size: int = 50
    ) -> tuple[Binder, list[BinderLifecycleLog], int] | None:
        binder = self.binder_repo.get_by_id(binder_id)
        if not binder:
            return None
        logs, total = self.log_repo.list_by_binder_page(binder_id, page, page_size)
        return binder, logs, total

    def get_binder_intakes(
        self, binder_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[BinderIntakeResponse], int]:
        binder = self.binder_repo.get_by_id(binder_id)
        if not binder:
            raise NotFoundError(
                BINDER_NOT_FOUND.format(binder_id=binder_id),
                "BINDER.NOT_FOUND",
            )

        intakes, total = self.intake_repo.list_by_binder_page(binder_id, page, page_size)

        # Batch-fetch user names to avoid N+1 queries.
        user_ids = {i.received_by for i in intakes}
        users = [self.user_repo.get_by_id(uid) for uid in user_ids]
        name_map = {u.id: u.full_name for u in users if u}

        result: list[BinderIntakeResponse] = []
        for intake in intakes:
            raw_materials = self.material_repo.list_by_intake(intake.id)
            material_responses = [
                BinderIntakeMaterialResponse.model_validate(m) for m in raw_materials
            ]
            result.append(
                BinderIntakeResponse(
                    id=intake.id,
                    binder_id=intake.binder_id,
                    received_at=intake.received_at,
                    received_by=intake.received_by,
                    received_by_name=name_map.get(intake.received_by),
                    notes=intake.notes,
                    created_at=intake.created_at,
                    materials=material_responses,
                )
            )
        return result, total
