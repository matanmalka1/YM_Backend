"""Audit helpers for charge lifecycle events."""

from app.audit.audit_constants import ENTITY_CHARGE
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter


def record_charge_status_audit(
    writer: EntityAuditWriter,
    charge_id: int,
    actor_id: int | None,
    action: str,
    old_status,
    new_status,
    note: str | None = None,
) -> None:
    writer.append(
        entity_type=ENTITY_CHARGE,
        entity_id=charge_id,
        actor_id=actor_id,
        action=action,
        old_value={"status": old_status},
        new_value={"status": new_status},
        note=note,
    )
