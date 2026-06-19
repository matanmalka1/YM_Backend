from sqlalchemy.orm import Session

from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.timeline.repositories.timeline_repository import TimelineRepository
from app.timeline.timeline_client_builders import (
    client_created_event,
    document_uploaded_event,
    signature_request_lifecycle_event,
)


def build_client_events(
    db: Session,
    client_record_id: int,
    business_ids: list[int],
) -> list[dict]:
    repo = TimelineRepository(db)
    events = []

    client_record = repo.get_client_record(client_record_id)
    client = (
        LegalEntityRepository(db).get_by_id(client_record.legal_entity_id)
        if client_record
        else None
    )
    if client:
        events.append(client_created_event(client))

    for doc in repo.list_permanent_documents(business_ids):
        events.append(document_uploaded_event(doc))

    for sig, audit_event in repo.list_signature_lifecycle_events(client_record_id):
        events.append(signature_request_lifecycle_event(sig, audit_event))

    return events
