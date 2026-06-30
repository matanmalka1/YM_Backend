from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_BINDER_CREATED,
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_MATERIAL_RECEIVED,
    ACTION_BINDER_REOPENED,
    ACTION_BINDER_REVERTED_READY,
    ENTITY_BINDER,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.binders.binder_audit import binder_metadata, lifecycle_value
from app.binders.binder_messages import (
    BINDER_CAPACITY_REOPENED,
    BINDER_HANDED_OVER,
    BINDER_HANDOVER_REVERTED,
    BINDER_MARKED_FULL,
    BINDER_MARKED_READY_FOR_HANDOVER,
    BINDER_NOT_FOUND,
    BINDER_RECEIVED,
)
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.models.binder_intake_material import BinderIntakeMaterial
from app.binders.repositories.binder_intake_material_repository import (
    BinderIntakeMaterialRepository,
)
from app.binders.repositories.binder_repository import BinderRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.notifications.models.notification import NotificationTrigger
from app.notifications.schemas.notification_schemas import NotificationResult
from app.notifications.services.notification_auto_send_service import NotificationAutoSendService
from app.utils.time_utils import israel_today, utcnow

ACTION_RECEIVE_MATERIAL = "receive_material"
ACTION_MARK_FULL = "mark_full"
ACTION_REOPEN_CAPACITY = "reopen_capacity"
ACTION_MARK_READY_FOR_HANDOVER = "mark_ready_for_handover"
ACTION_REVERT_READY_FOR_HANDOVER = "revert_ready_for_handover"
ACTION_HANDOVER_TO_CLIENT = "handover_to_client"


class BinderLifecycleService:
    """Owns binder lifecycle state transitions and their side effects."""

    def __init__(self, db: Session):
        self.db = db
        self.binder_repo = BinderRepository(db)
        self.material_repo = BinderIntakeMaterialRepository(db)
        self.audit_writer = EntityAuditWriter(db)
        self.auto_send_service = NotificationAutoSendService(db)

    @staticmethod
    def get_available_action_keys(binder: Binder) -> list[str]:
        return BinderLifecycleService.get_available_action_keys_for_state(
            location_status=binder.location_status,
            capacity_status=binder.capacity_status,
        )

    @staticmethod
    def get_available_action_keys_for_state(
        *,
        location_status: BinderLocationStatus,
        capacity_status: BinderCapacityStatus,
    ) -> list[str]:
        location = location_status
        capacity = capacity_status
        if location == BinderLocationStatus.IN_OFFICE:
            actions = [ACTION_MARK_READY_FOR_HANDOVER]
            if capacity == BinderCapacityStatus.OPEN:
                actions.extend([ACTION_RECEIVE_MATERIAL, ACTION_MARK_FULL])
            else:
                actions.append(ACTION_REOPEN_CAPACITY)
            return actions
        if location == BinderLocationStatus.READY_FOR_HANDOVER:
            return [ACTION_REVERT_READY_FOR_HANDOVER, ACTION_HANDOVER_TO_CLIENT]
        return []

    @staticmethod
    def is_intake_eligible(binder: Binder) -> bool:
        return (
            binder.location_status == BinderLocationStatus.IN_OFFICE
            and binder.capacity_status == BinderCapacityStatus.OPEN
        )

    def receive_material(
        self,
        binder: Binder,
        changed_by_user_id: int,
        *,
        allow_full_in_office: bool = False,
        actor_display_name: str | None = None,
    ) -> Binder:
        eligible = self.is_intake_eligible(binder) or (
            allow_full_in_office
            and binder.location_status == BinderLocationStatus.IN_OFFICE
            and binder.capacity_status == BinderCapacityStatus.FULL
        )
        if not eligible:
            raise AppError(
                "לא ניתן לקלוט חומר לקלסר במצב הנוכחי", ErrorCode.BINDER_NOT_INTAKE_ELIGIBLE
            )
        self._record(
            binder,
            ACTION_BINDER_MATERIAL_RECEIVED,
            "capacity_status",
            binder.capacity_status.value,
            binder.capacity_status.value,
            changed_by_user_id,
            actor_display_name,
            BINDER_RECEIVED,
        )
        return binder

    def receive_material_by_id(
        self,
        binder_id: int,
        changed_by_user_id: int,
        actor_display_name: str | None = None,
    ) -> Binder:
        binder = self._get_for_update(binder_id)
        return self.receive_material(
            binder, changed_by_user_id, actor_display_name=actor_display_name
        )

    def mark_full(
        self,
        binder_id: int,
        changed_by_user_id: int,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> Binder:
        binder = self._get_for_update(binder_id)
        self._ensure_capacity_change_allowed(binder)
        if binder.capacity_status == BinderCapacityStatus.FULL:
            raise AppError("הקלסר כבר מלא", ErrorCode.BINDER_ALREADY_FULL)
        return self._set_capacity(
            binder,
            BinderCapacityStatus.FULL,
            ACTION_BINDER_MARKED_FULL,
            changed_by_user_id,
            notes or BINDER_MARKED_FULL,
            actor_display_name,
        )

    def reopen_capacity(
        self,
        binder_id: int,
        changed_by_user_id: int,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> Binder:
        binder = self._get_for_update(binder_id)
        self._ensure_capacity_change_allowed(binder)
        if binder.capacity_status == BinderCapacityStatus.OPEN:
            raise AppError("הקלסר אינו מלא", ErrorCode.BINDER_NOT_FULL)
        return self._set_capacity(
            binder,
            BinderCapacityStatus.OPEN,
            ACTION_BINDER_REOPENED,
            changed_by_user_id,
            notes or BINDER_CAPACITY_REOPENED,
            actor_display_name,
        )

    def mark_ready_for_handover(
        self,
        binder_id: int,
        changed_by_user_id: int,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> tuple[Binder, NotificationResult]:
        binder = self._get_for_update(binder_id)
        if binder.location_status != BinderLocationStatus.IN_OFFICE:
            raise AppError(
                "לא ניתן לסמן קלסר כמוכן למסירה מהמצב הנוכחי",
                ErrorCode.BINDER_INVALID_LOCATION_TRANSITION,
            )
        old_value = binder.location_status.value
        binder.location_status = BinderLocationStatus.READY_FOR_HANDOVER
        binder.ready_for_handover_at = utcnow()
        self.db.flush()
        self._record(
            binder,
            ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
            "location_status",
            old_value,
            BinderLocationStatus.READY_FOR_HANDOVER.value,
            changed_by_user_id,
            actor_display_name,
            notes or BINDER_MARKED_READY_FOR_HANDOVER,
        )
        if binder.client_record_id:
            idempotency_key = f"binder_ready_{binder.id}_{binder.ready_for_handover_at.isoformat()}"
            notification_result = self.auto_send_service.auto_send(
                trigger=NotificationTrigger.BINDER_READY_FOR_HANDOVER,
                client_record_id=binder.client_record_id,
                entity_id=binder.id,
                binder_id=binder.id,
                entity_type="binder",
                triggered_by=changed_by_user_id,
                idempotency_key=idempotency_key,
            )
        else:
            notification_result = NotificationResult(
                status="skipped",
                reason="קלסר אינו משויך ללקוח",
            )
        return binder, notification_result

    def mark_ready_for_handover_bulk(
        self,
        client_record_id: int,
        until_period_year: int,
        until_period_month: int,
        changed_by_user_id: int,
        actor_display_name: str | None = None,
    ) -> list[tuple[Binder, NotificationResult]]:
        cutoff = (until_period_year, until_period_month)
        updated: list[tuple[Binder, NotificationResult]] = []
        for binder in self.binder_repo.list_by_client_record(client_record_id):
            if binder.location_status != BinderLocationStatus.IN_OFFICE:
                continue
            latest_material = self.material_repo.get_last_by_binder(binder.id)
            if not self._material_period_lte_cutoff(latest_material, cutoff):
                continue
            updated.append(
                self.mark_ready_for_handover(
                    binder.id,
                    changed_by_user_id=changed_by_user_id,
                    actor_display_name=actor_display_name,
                )
            )
        return updated

    def revert_ready_for_handover(
        self,
        binder_id: int,
        changed_by_user_id: int,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> Binder:
        binder = self._get_for_update(binder_id)
        if binder.location_status != BinderLocationStatus.READY_FOR_HANDOVER:
            raise AppError(
                "לא ניתן לבטל מוכנות למסירה מהמצב הנוכחי",
                ErrorCode.BINDER_INVALID_LOCATION_TRANSITION,
            )
        old_value = binder.location_status.value
        binder.location_status = BinderLocationStatus.IN_OFFICE
        self.db.flush()
        self._record(
            binder,
            ACTION_BINDER_REVERTED_READY,
            "location_status",
            old_value,
            BinderLocationStatus.IN_OFFICE.value,
            changed_by_user_id,
            actor_display_name,
            notes or BINDER_HANDOVER_REVERTED,
        )
        return binder

    def handover_to_client(
        self,
        binder_id: int,
        changed_by_user_id: int,
        handed_over_at: date | None = None,
        handover_recipient_name: str | None = None,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> Binder:
        binder = self._get_for_update(binder_id)
        return self.handover_loaded_binder(
            binder,
            changed_by_user_id=changed_by_user_id,
            handed_over_at=handed_over_at,
            handover_recipient_name=handover_recipient_name,
            notes=notes,
            actor_display_name=actor_display_name,
        )

    def handover_loaded_binder(
        self,
        binder: Binder,
        changed_by_user_id: int,
        handed_over_at: date | None = None,
        handover_recipient_name: str | None = None,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> Binder:
        if binder.location_status == BinderLocationStatus.HANDED_OVER:
            raise AppError("הקלסר כבר נמסר ללקוח", ErrorCode.BINDER_ALREADY_HANDED_OVER)
        if binder.location_status != BinderLocationStatus.READY_FOR_HANDOVER:
            raise AppError("הקלסר אינו מוכן למסירה", ErrorCode.BINDER_NOT_READY_FOR_HANDOVER)
        old_value = binder.location_status.value
        effective_handover_at = handed_over_at or israel_today()
        binder.location_status = BinderLocationStatus.HANDED_OVER
        binder.handed_over_at = effective_handover_at
        binder.handover_recipient_name = handover_recipient_name
        if binder.period_end is None:
            binder.period_end = effective_handover_at
        self.db.flush()
        self._record(
            binder,
            ACTION_BINDER_HANDED_OVER,
            "location_status",
            old_value,
            BinderLocationStatus.HANDED_OVER.value,
            changed_by_user_id,
            actor_display_name,
            notes or BINDER_HANDED_OVER,
        )
        return binder

    def _get_for_update(self, binder_id: int) -> Binder:
        binder = self.binder_repo.get_by_id_for_update(binder_id)
        if not binder:
            raise NotFoundError(
                BINDER_NOT_FOUND.format(binder_id=binder_id), ErrorCode.BINDER_NOT_FOUND
            )
        return binder

    @staticmethod
    def _ensure_capacity_change_allowed(binder: Binder) -> None:
        if binder.location_status == BinderLocationStatus.HANDED_OVER:
            raise AppError("הקלסר כבר נמסר ללקוח", ErrorCode.BINDER_ALREADY_HANDED_OVER)
        if binder.location_status != BinderLocationStatus.IN_OFFICE:
            raise AppError(
                "לא ניתן לשנות קיבולת כשהקלסר אינו במשרד",
                ErrorCode.BINDER_CAPACITY_CHANGE_NOT_ALLOWED,
            )

    def _set_capacity(
        self,
        binder: Binder,
        new_value: BinderCapacityStatus,
        action: str,
        changed_by_user_id: int,
        notes: str | None,
        actor_display_name: str | None,
    ) -> Binder:
        old_value = binder.capacity_status.value
        binder.capacity_status = new_value
        self.db.flush()
        self._record(
            binder,
            action,
            "capacity_status",
            old_value,
            new_value.value,
            changed_by_user_id,
            actor_display_name,
            notes,
        )
        return binder

    def _record(
        self,
        binder: Binder,
        action: str,
        field_name: str,
        old_value: str,
        new_value: str,
        changed_by_user_id: int,
        actor_display_name: str | None,
        notes: str | None,
    ) -> None:
        """Append a binder lifecycle audit row to EntityAuditLog (§10b/§17)."""
        self.audit_writer.record_action(
            ENTITY_BINDER,
            binder.id,
            changed_by_user_id,
            action,
            old_value=lifecycle_value(field_name, old_value),
            new_value=lifecycle_value(field_name, new_value),
            note=notes,
            actor_display_name=actor_display_name,
            metadata_json=binder_metadata(binder),
        )

    @staticmethod
    def _material_period_lte_cutoff(
        material: BinderIntakeMaterial | None,
        cutoff: tuple[int, int],
    ) -> bool:
        if not material or material.period_year is None or material.period_month_end is None:
            return False
        return (material.period_year, material.period_month_end) <= cutoff

    def log_initial_state(
        self,
        binder: Binder,
        changed_by_user_id: int,
        notes: str | None = None,
        actor_display_name: str | None = None,
    ) -> None:
        """Record the binder's creation as one ``binder.created`` audit row.

        Replaces the two legacy ``null -> in_office`` / ``null -> open`` lifecycle
        rows; both initial statuses are carried in ``new_value``.
        """
        self.audit_writer.record_action(
            ENTITY_BINDER,
            binder.id,
            changed_by_user_id,
            ACTION_BINDER_CREATED,
            new_value={
                "location_status": binder.location_status.value,
                "capacity_status": binder.capacity_status.value,
            },
            note=notes or BINDER_RECEIVED,
            actor_display_name=actor_display_name,
            metadata_json=binder_metadata(binder),
        )
