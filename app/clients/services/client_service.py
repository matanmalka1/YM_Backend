from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.services.client_messages import CLIENT_NOT_FOUND
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


def get_client_or_raise(db: Session, client_id: int) -> ClientRecord:
    client = ClientRecordRepository(db).get_by_id(client_id)
    if not client:
        raise NotFoundError(
            CLIENT_NOT_FOUND.format(client_id=client_id), ErrorCode.CLIENT_RECORD_NOT_FOUND
        )
    return client
