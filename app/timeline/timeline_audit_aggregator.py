"""Surface entity audit-log rows (the 'יומן שינויים' feed) as timeline events.

Each audited entity related to a client — the client record, its businesses,
charges and annual reports — contributes its full change log. Actions already
represented by richer, domain-derived timeline events are skipped to avoid
duplicates.
"""

from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_CREATED,
    ACTION_ISSUED,
    ACTION_PAID,
    ACTION_STATUS_CHANGED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
)
from app.audit.repositories.audit_entity_audit_log_repository import EntityAuditLogRepository
from app.timeline.timeline_client_builders import entity_audit_changed_event
from app.users.repositories.user_repository import UserRepository

# Actions already shown as dedicated, richer timeline events — skipped here.
_DEDUP_ACTIONS = {
    ENTITY_CLIENT: {ACTION_CREATED},  # client_created
    ENTITY_ANNUAL_REPORT: {ACTION_STATUS_CHANGED},  # annual_report_status_changed
    ENTITY_CHARGE: {ACTION_CREATED, ACTION_ISSUED, ACTION_PAID},  # charge_* events
    ENTITY_BUSINESS: set(),
}


def build_entity_audit_events(
    db: Session,
    *,
    client_record_id: int,
    business_ids: list[int],
    charge_ids: list[int],
    report_ids: list[int],
) -> list[dict]:
    repo = EntityAuditLogRepository(db)
    scopes = (
        (ENTITY_CLIENT, [client_record_id]),
        (ENTITY_BUSINESS, business_ids),
        (ENTITY_CHARGE, charge_ids),
        (ENTITY_ANNUAL_REPORT, report_ids),
    )

    rows = []
    for entity_type, entity_ids in scopes:
        dedup = _DEDUP_ACTIONS[entity_type]
        rows.extend(
            row
            for row in repo.list_all_by_entities(entity_type, entity_ids)
            if row.action not in dedup
        )

    if not rows:
        return []

    user_ids = list({row.performed_by for row in rows})
    name_by_id = {user.id: user.full_name for user in UserRepository(db).list_by_ids(user_ids)}

    return [entity_audit_changed_event(row, name_by_id.get(row.performed_by)) for row in rows]
