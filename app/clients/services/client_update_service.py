import logging

from sqlalchemy.orm import Session

from app.actions.services.obligation_orchestrator import (
    generate_client_obligations,
    obligation_fields_changed,
)
from app.annual_reports.services.annual_report_client_status_service import (
    AnnualReportClientStatusService,
)
from app.audit.audit_constants import (
    ACTION_ENTITY_TYPE_CHANGED,
    ACTION_LEGAL_ENTITY_UPDATED,
    ACTION_PERSON_UPDATED,
    ENTITY_CLIENT,
    ENTITY_LEGAL_ENTITY,
    ENTITY_PERSON,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.binders.repositories.binder_repository import BinderRepository
from app.clients.client_enums import ClientStatus
from app.clients.repositories.client_graph_writer import apply_graph_update
from app.clients.repositories.client_record_read_repository import (
    get_full_record,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import ForbiddenError, NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.legal_entities.repositories.person_repository import PersonRepository
from app.users.models.user import UserRole
from app.utils.time_utils import israel_today
from app.vat.services.vat_client_status_service import (
    VatWorkItemClientStatusService,
)

_log = logging.getLogger(__name__)


class ClientUpdateService:
    def __init__(self, db: Session):
        self.db = db
        self.record_repo = ClientRecordRepository(db)
        self._audit = EntityAuditWriter(db)
        self.legal_entity_repo = LegalEntityRepository(db)
        self.person_repo = PersonRepository(db)

    def update_client(
        self,
        client_id: int,
        actor_id: int | None = None,
        actor_role=None,
        actor_name: str | None = None,
        **fields,
    ):
        existing = get_full_record(self.db, client_id)
        if not existing:
            raise NotFoundError(f"לקוח {client_id} לא נמצא", ErrorCode.CLIENT_RECORD_NOT_FOUND)
        new_status = fields.get("status")
        new_entity_type = fields.get("entity_type")
        old_entity_type = existing.get("entity_type")
        # advance_rate_updated_at is server-owned: stamp it only when advance_rate
        # is actually changing, comparing against the already-loaded record.
        if "advance_rate" in fields and fields["advance_rate"] != existing.get("advance_rate"):
            fields["advance_rate_updated_at"] = israel_today()
        if new_entity_type is not None and new_entity_type != old_entity_type:
            if actor_role != UserRole.ADVISOR:
                raise ForbiddenError(
                    "שינוי סוג ישות מותר לרואה חשבון בלבד",
                    ErrorCode.CLIENT_ENTITY_TYPE_CHANGE_FORBIDDEN,
                )
            self._cancel_deadlines_on_entity_type_change(
                client_id, old_entity_type, new_entity_type, actor_id, actor_name
            )
        old_snapshot = {k: existing.get(k) for k in fields if k in existing}
        record = self.record_repo.get_by_id(client_id)
        legal_entity = (
            self.legal_entity_repo.get_by_id(record.legal_entity_id) if record is not None else None
        )
        person = (
            self.person_repo.get_owner_for_legal_entity(legal_entity.id)
            if legal_entity is not None
            else None
        )
        old_legal_snapshot = self._legal_entity_audit_snapshot(legal_entity, fields)
        old_person_snapshot = self._person_audit_snapshot(person, fields)
        updated = self._update_client_record_graph(client_id, **fields)
        if new_status is not None:
            self._update_client_record_status(client_id, new_status)
        if obligation_fields_changed(fields):
            generate_client_obligations(
                self.db,
                client_id,
                actor_id=actor_id,
                entity_type=updated.get("entity_type"),
                best_effort=True,
            )
        self._audit.record_update(
            ENTITY_CLIENT,
            client_id,
            actor_id,
            old_value=old_snapshot,
            new_value={k: updated.get(k) for k in fields},
            actor_display_name=actor_name,
            metadata_json={"client_record_id": client_id},
        )
        if legal_entity is not None and old_legal_snapshot:
            self._audit.record_action(
                ENTITY_LEGAL_ENTITY,
                legal_entity.id,
                actor_id,
                ACTION_LEGAL_ENTITY_UPDATED,
                old_value=old_legal_snapshot,
                new_value=self._legal_entity_audit_snapshot(legal_entity, fields),
                actor_display_name=actor_name,
                metadata_json={"client_record_id": client_id, "legal_entity_id": legal_entity.id},
            )
        if person is not None and old_person_snapshot:
            self._audit.record_action(
                ENTITY_PERSON,
                person.id,
                actor_id,
                ACTION_PERSON_UPDATED,
                old_value=old_person_snapshot,
                new_value=self._person_audit_snapshot(person, fields),
                actor_display_name=actor_name,
                metadata_json={
                    "client_record_id": client_id,
                    "legal_entity_id": legal_entity.id if legal_entity is not None else None,
                    "person_id": person.id,
                },
            )
        return updated

    def _legal_entity_audit_snapshot(self, legal_entity, fields: dict) -> dict:
        if legal_entity is None:
            return {}
        mapping = {
            "full_name": "official_name",
            "entity_type": "entity_type",
            "vat_reporting_frequency": "vat_reporting_frequency",
            "advance_payment_frequency": "advance_payment_frequency",
            "advance_rate": "advance_rate",
            "advance_rate_updated_at": "advance_rate_updated_at",
            "annual_revenue": "annual_revenue",
        }
        return {
            target: getattr(legal_entity, target)
            for source, target in mapping.items()
            if source in fields
        }

    def _person_audit_snapshot(self, person, fields: dict) -> dict:
        if person is None:
            return {}
        person_fields = {
            "full_name",
            "phone",
            "email",
            "address_street",
            "address_building_number",
            "address_apartment",
            "address_city",
            "address_zip_code",
        }
        return {key: getattr(person, key) for key in person_fields if key in fields}

    def _update_client_record_graph(self, client_id: int, **fields):
        return apply_graph_update(self.db, client_id, **fields)

    def _update_client_record_status(self, client_id: int, new_status: ClientStatus) -> None:
        record = self.record_repo.get_by_id(client_id)
        if not record:
            return
        self.record_repo.update_status(record.id, new_status)
        if new_status in {ClientStatus.CLOSED, ClientStatus.FROZEN}:
            VatWorkItemClientStatusService(self.db).cancel_open_by_client_record(record.id)
            AnnualReportClientStatusService(self.db).cancel_open_by_client_record(record.id)
            BinderRepository(self.db).close_in_office_by_client_record(record.id)

    def _cancel_deadlines_on_entity_type_change(
        self, client_id: int, old_entity_type, new_entity_type, actor_id, actor_name=None
    ):
        record = self.record_repo.get_by_id(client_id)
        if not record:
            return
        _log.warning(
            "entity_type_changed: client_id=%s old=%s new=%s actor=%s",
            client_id,
            old_entity_type,
            new_entity_type,
            actor_id,
        )
        self._audit.record_action(
            ENTITY_CLIENT,
            client_id,
            actor_id,
            ACTION_ENTITY_TYPE_CHANGED,
            old_value={"entity_type": old_entity_type},
            new_value={"entity_type": new_entity_type},
            actor_display_name=actor_name,
            metadata_json={"client_record_id": client_id},
        )
