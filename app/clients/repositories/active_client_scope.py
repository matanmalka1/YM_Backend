from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity


def scope_to_active_clients_stmt(stmt, owner_model, *, join_legal_entity: bool = False):
    """Restrict a statement to rows whose owning client record is active (not soft-deleted).

    When ``join_legal_entity`` is set, also joins ``LegalEntity`` so callers can add
    predicates or projections against it without re-joining. The scope predicate is
    unchanged; the extra join only widens what is available, never what passes.
    """
    stmt = stmt.join(ClientRecord, ClientRecord.id == owner_model.client_record_id)
    if join_legal_entity:
        stmt = stmt.join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
    return stmt.where(ClientRecord.deleted_at.is_(None))
