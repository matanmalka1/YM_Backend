from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity


def eligible_client_status_expr():
    """The SQL twin of ``assert_client_record_is_active``.

    A set-based command (bulk generation) cannot call a per-row Python guard, so
    the rule has to exist in both forms. They must change together: a client the
    guard rejects must be a client this predicate excludes.

    An allowlist, not "everything except closed and frozen", per
    ``docs/agent/decision-making.md``: a status added later must not become
    silently eligible.
    """
    return ClientRecord.status == ClientStatus.ACTIVE


def scope_to_active_clients_stmt(stmt, owner_model, *, join_legal_entity: bool = False):
    """Restrict a statement to rows whose owning client record is active (not soft-deleted).

    Pass ``ClientRecord`` as ``owner_model`` when the statement already selects
    client records themselves — it owns itself, so there is no join to add, only
    the scope predicate. Every other model is joined through its
    ``client_record_id``.

    When ``join_legal_entity`` is set, also joins ``LegalEntity`` so callers can add
    predicates or projections against it without re-joining. The scope predicate is
    unchanged; the extra join only widens what is available, never what passes.
    """
    if owner_model is not ClientRecord:
        stmt = stmt.join(ClientRecord, ClientRecord.id == owner_model.client_record_id)
    if join_legal_entity:
        stmt = stmt.join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
    return stmt.where(ClientRecord.deleted_at.is_(None))
