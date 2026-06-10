import logging

from sqlalchemy.orm import Session

from app.actions.services.obligation_orchestrator import (
    generate_client_obligations,
    obligation_fields_changed,
)
from app.annual_reports.services.client_status_service import (
    AnnualReportClientStatusService,
)
from app.audit.constants import ACTION_ENTITY_TYPE_CHANGED, ENTITY_CLIENT
from app.audit.services.entity_audit_writer import EntityAuditWriter
from app.binders.repositories.binder_repository import BinderRepository
from app.clients.enums import ClientStatus
from app.clients.repositories.client_graph_writer import apply_graph_update
from app.clients.repositories.client_record_read_repository import (
    get_full_record,
)
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import ForbiddenError, NotFoundError
from app.users.models.user import UserRole
from app.vat.services.client_status_service import (
    VatWorkItemClientStatusService,
)

_log = logging.getLogger(__name__)


class ClientUpdateService:
    def __init__(self, db: Session):
        self.db = db
        self.record_repo = ClientRecordRepository(db)
        self._audit = EntityAuditWriter(db)

    def update_client(self, client_id: int, actor_id: int | None = None, actor_role=None, **fields):
        existing = get_full_record(self.db, client_id)
        if not existing:
            raise NotFoundError(f"לקוח {client_id} לא נמצא", "CLIENT.NOT_FOUND")
        new_status = fields.get("status")
        new_entity_type = fields.get("entity_type")
        old_entity_type = existing.get("entity_type")
        if new_entity_type is not None and new_entity_type != old_entity_type:
            if actor_role != UserRole.ADVISOR:
                raise ForbiddenError(
                    "שינוי סוג ישות מותר לרואה חשבון בלבד",
                    "CLIENT.ENTITY_TYPE_CHANGE_FORBIDDEN",
                )
            self._cancel_deadlines_on_entity_type_change(
                client_id, old_entity_type, new_entity_type, actor_id
            )
        old_snapshot = {k: existing.get(k) for k in fields if k in existing}
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
        )
        return updated

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
        self, client_id: int, old_entity_type, new_entity_type, actor_id
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
        self._audit.record_update(
            ENTITY_CLIENT,
            client_id,
            actor_id,
            old_value={"entity_type": old_entity_type},
            new_value={"entity_type": new_entity_type},
            note=ACTION_ENTITY_TYPE_CHANGED,
        )
