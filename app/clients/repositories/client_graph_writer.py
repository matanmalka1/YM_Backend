from app.core.error_codes import ErrorCode
from sqlalchemy.orm import Session

from app.clients.repositories.client_record_read_repository import get_full_record
from app.clients.services.client_service import get_client_or_raise
from app.core.exceptions import NotFoundError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.legal_entities.repositories.person_repository import PersonRepository

_PERSON_FIELDS = frozenset(
    {
        "phone",
        "email",
        "address_street",
        "address_building_number",
        "address_apartment",
        "address_city",
        "address_zip_code",
    }
)
_LEGAL_ENTITY_FIELDS = frozenset(
    {
        "entity_type",
        "vat_reporting_frequency",
        "advance_payment_frequency",
        "advance_rate",
        "advance_rate_updated_at",
        "annual_revenue",
    }
)
_RECORD_FIELDS = frozenset({"status", "accountant_id"})


def apply_graph_update(db: Session, client_id: int, **fields) -> dict:
    """Apply **fields to the Person / LegalEntity / ClientRecord graph and flush.

    Returns the refreshed full-record dict, or raises NotFoundError.
    """
    record = get_client_or_raise(db, client_id)
    legal_entity = LegalEntityRepository(db).get_by_id(record.legal_entity_id)
    if not legal_entity:
        raise NotFoundError(f"לקוח {client_id} לא נמצא", ErrorCode.CLIENT_RECORD_NOT_FOUND)
    person = PersonRepository(db).get_owner_for_legal_entity(legal_entity.id)
    if "full_name" in fields:
        legal_entity.official_name = fields["full_name"]
        if person is not None:
            person.full_name = fields["full_name"]
    for key, value in fields.items():
        if key in _PERSON_FIELDS and person is not None:
            setattr(person, key, value)
        elif key in _LEGAL_ENTITY_FIELDS:
            setattr(legal_entity, key, value)
        elif key in _RECORD_FIELDS:
            setattr(record, key, value)
    db.flush()
    updated = get_full_record(db, client_id)
    if not updated:
        raise NotFoundError(f"לקוח {client_id} לא נמצא", ErrorCode.CLIENT_RECORD_NOT_FOUND)
    return updated
