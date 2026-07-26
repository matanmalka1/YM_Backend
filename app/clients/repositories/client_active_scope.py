from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity


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
