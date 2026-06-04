"""
Intake edit service with field-level audit trail.

Handles editing of BinderIntake fields and cross-client transfer with FK validation.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.binders.models.binder_intake import BinderIntake
from app.binders.models.binder_intake_material import BinderIntakeMaterial
from app.binders.repositories.binder_intake_edit_log_repository import (
    BinderIntakeEditLogRepository,
)
from app.binders.repositories.binder_intake_material_repository import (
    BinderIntakeMaterialRepository,
)
from app.binders.repositories.binder_intake_repository import BinderIntakeRepository
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.messages import (
    BINDER_INTAKE_CROSS_CLIENT_VALIDATION_FAILED,
    BINDER_INTAKE_NOT_FOUND,
    BINDER_NOT_FOUND,
)
from app.businesses.repositories.business_repository import BusinessRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import AppError, NotFoundError
from app.vat_reports.repositories.vat_work_item_write_repository import (
    VatWorkItemWriteRepository as VatWorkItemRepository,
)

_PATCHABLE_INTAKE_FIELDS = {"received_at", "received_by", "notes"}
_TRANSFER_LIST_KEYS = {
    "business_ids": "business_id",
    "annual_report_ids": "annual_report_id",
    "vat_report_ids": "vat_report_id",
}


class BinderIntakeEditService:
    """Edit BinderIntake with field-level audit trail and FK cross-client validation."""

    def __init__(self, db: Session):
        self.db = db
        self.intake_repo = BinderIntakeRepository(db)
        self.material_repo = BinderIntakeMaterialRepository(db)
        self.edit_log_repo = BinderIntakeEditLogRepository(db)
        self.client_record_repo = ClientRecordRepository(db)
        self.binder_repo = BinderRepository(db)
        self.business_repo = BusinessRepository(db)
        self.annual_report_repo = AnnualReportRepository(db)
        self.vat_report_repo = VatWorkItemRepository(db)

    def edit_intake(
        self,
        intake_id: int,
        actor_id: int,
        patch: dict[str, Any],
        binder_id: int | None = None,
    ) -> BinderIntake:
        """
        Apply a partial update to a BinderIntake.

        Supported patch keys:
        - intake fields: received_at, received_by, notes
        - transfer fields: client_record_id, binder_id
        - linked FK replacements: business_ids, annual_report_ids, vat_report_ids

        binder_id: when provided, the intake must belong to that binder (scoped lookup).
        """
        intake = self.intake_repo.get_by_id(intake_id)
        if not intake or (binder_id is not None and intake.binder_id != binder_id):
            raise NotFoundError(BINDER_INTAKE_NOT_FOUND, "BINDER_INTAKE.NOT_FOUND")

        normalized_patch = self._normalize_patch(patch)

        for field in _PATCHABLE_INTAKE_FIELDS:
            if field not in normalized_patch:
                continue
            self._apply_logged_change(
                intake=intake,
                actor_id=actor_id,
                field_name=field,
                target=intake,
                attr_name=field,
                new_value=normalized_patch[field],
            )

        if self._is_transfer_patch(normalized_patch):
            self._apply_transfer_patch(intake=intake, actor_id=actor_id, patch=normalized_patch)

        self.db.flush()
        return intake

    @staticmethod
    def _normalize_patch(patch: dict[str, Any]) -> dict[str, Any]:
        return dict(patch)

    @staticmethod
    def _is_transfer_patch(patch: dict[str, Any]) -> bool:
        return any(
            key in patch for key in {"client_record_id", "binder_id", *tuple(_TRANSFER_LIST_KEYS)}
        )

    def _apply_transfer_patch(
        self,
        *,
        intake: BinderIntake,
        actor_id: int,
        patch: dict[str, Any],
    ) -> None:
        current_binder = self.binder_repo.get_by_id(intake.binder_id)
        if not current_binder:
            raise NotFoundError(
                BINDER_NOT_FOUND.format(binder_id=intake.binder_id),
                "BINDER.NOT_FOUND",
            )

        target_binder = self._resolve_target_binder(current_binder=current_binder, patch=patch)
        target_client_id = target_binder.client_record_id
        target_client_record = self.client_record_repo.get_by_id(target_client_id)
        if not target_client_record:
            raise AppError(BINDER_INTAKE_CROSS_CLIENT_VALIDATION_FAILED, "BINDER.CROSS_CLIENT")
        target_legal_entity_id = target_client_record.legal_entity_id

        if current_binder.client_record_id != target_client_id:
            self.edit_log_repo.append(
                intake_id=intake.id,
                field_name="client_record_id",
                old_value=self._stringify_value(current_binder.client_record_id),
                new_value=self._stringify_value(target_client_id),
                changed_by=actor_id,
            )

        materials = self.material_repo.list_by_intake(intake.id)
        self._validate_and_apply_fk_updates(
            intake=intake,
            actor_id=actor_id,
            materials=materials,
            attr_name="business_id",
            replacements=patch.get("business_ids"),
            client_record_id=target_legal_entity_id,
            loader=self.business_repo.get_by_id,
            owner_attr="legal_entity_id",
        )
        self._validate_and_apply_fk_updates(
            intake=intake,
            actor_id=actor_id,
            materials=materials,
            attr_name="annual_report_id",
            replacements=patch.get("annual_report_ids"),
            client_record_id=target_client_id,
            loader=self.annual_report_repo.get_by_id,
            owner_attr="client_record_id",
        )
        self._validate_and_apply_fk_updates(
            intake=intake,
            actor_id=actor_id,
            materials=materials,
            attr_name="vat_report_id",
            replacements=patch.get("vat_report_ids"),
            client_record_id=target_client_id,
            loader=self.vat_report_repo.get_by_id,
            owner_attr="client_record_id",
        )

        if intake.binder_id != target_binder.id:
            self._apply_logged_change(
                intake=intake,
                actor_id=actor_id,
                field_name="binder_id",
                target=intake,
                attr_name="binder_id",
                new_value=target_binder.id,
            )

    def _resolve_target_binder(
        self,
        *,
        current_binder,
        patch: dict[str, Any],
    ):
        requested_binder_id = patch.get("binder_id")
        requested_client_record_id = patch.get("client_record_id")

        if requested_binder_id is not None:
            target_binder = self.binder_repo.get_by_id(requested_binder_id)
            if not target_binder:
                raise NotFoundError(
                    BINDER_NOT_FOUND.format(binder_id=requested_binder_id),
                    "BINDER.NOT_FOUND",
                )
            if (
                requested_client_record_id is not None
                and target_binder.client_record_id != requested_client_record_id
            ):
                raise AppError(BINDER_INTAKE_CROSS_CLIENT_VALIDATION_FAILED, "BINDER.CROSS_CLIENT")
            return target_binder

        if (
            requested_client_record_id is None
            or requested_client_record_id == current_binder.client_record_id
        ):
            return current_binder

        target_binder = self.binder_repo.get_active_by_client_record(requested_client_record_id)
        if not target_binder:
            raise AppError(BINDER_INTAKE_CROSS_CLIENT_VALIDATION_FAILED, "BINDER.CROSS_CLIENT")
        return target_binder

    def _validate_and_apply_fk_updates(
        self,
        *,
        intake: BinderIntake,
        actor_id: int,
        materials: list[BinderIntakeMaterial],
        attr_name: str,
        replacements: list[int] | None,
        client_record_id: int,
        loader,
        owner_attr: str,
    ) -> None:
        linked_materials = [m for m in materials if getattr(m, attr_name) is not None]

        if replacements is not None and len(replacements) != len(linked_materials):
            raise AppError(BINDER_INTAKE_CROSS_CLIENT_VALIDATION_FAILED, "BINDER.CROSS_CLIENT")

        effective_ids = replacements or [getattr(m, attr_name) for m in linked_materials]
        for idx, entity_id in enumerate(effective_ids):
            entity = loader(entity_id)
            if not entity or getattr(entity, owner_attr, None) != client_record_id:
                raise AppError(BINDER_INTAKE_CROSS_CLIENT_VALIDATION_FAILED, "BINDER.CROSS_CLIENT")

            if replacements is None:
                continue

            material = linked_materials[idx]
            if getattr(material, attr_name) == entity_id:
                continue

            self._apply_logged_change(
                intake=intake,
                actor_id=actor_id,
                field_name=f"material:{material.id}.{attr_name}",
                target=material,
                attr_name=attr_name,
                new_value=entity_id,
            )

    def _apply_logged_change(
        self,
        *,
        intake: BinderIntake,
        actor_id: int,
        field_name: str,
        target: Any,
        attr_name: str,
        new_value: Any,
    ) -> None:
        old_value = getattr(target, attr_name, None)
        if old_value == new_value:
            return

        self.edit_log_repo.append(
            intake_id=intake.id,
            field_name=field_name,
            old_value=self._stringify_value(old_value),
            new_value=self._stringify_value(new_value),
            changed_by=actor_id,
        )
        setattr(target, attr_name, new_value)

    @staticmethod
    def _stringify_value(value: Any) -> str | None:
        return str(value) if value is not None else None
