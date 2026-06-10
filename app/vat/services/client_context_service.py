from sqlalchemy.orm import Session

from app.clients.guards.client_record_guards import assert_client_record_is_active
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.repositories.legal_entity_repository import LegalEntityRepository
from app.core.exceptions import NotFoundError
from app.vat.services.messages import VAT_CLIENT_NOT_FOUND


class VatClientContextService:
    def __init__(self, db: Session):
        self.record_repo = ClientRecordRepository(db)
        self.legal_entity_repo = LegalEntityRepository(db)

    def get_active_client_and_entity(self, client_record_id: int):
        client_record = self.record_repo.get_by_id(client_record_id)
        if not client_record:
            raise NotFoundError(
                VAT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                "VAT.NOT_FOUND",
            )
        assert_client_record_is_active(client_record)
        legal_entity = self.legal_entity_repo.get_by_id(client_record.legal_entity_id)
        if not legal_entity:
            raise NotFoundError(
                VAT_CLIENT_NOT_FOUND.format(client_record_id=client_record_id),
                "VAT.NOT_FOUND",
            )
        return client_record, legal_entity
