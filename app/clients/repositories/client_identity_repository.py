from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity


@dataclass(frozen=True, slots=True)
class ClientDisplayProfile:
    client_name: str
    office_client_number: int | None


class ClientIdentityRepository(BaseRepository[ClientRecord]):
    model = ClientRecord

    def __init__(self, db: Session):
        super().__init__(db)

    def get_display_map(self, client_record_ids: Iterable[int]) -> dict[int, ClientDisplayProfile]:
        ids = list(set(client_record_ids))
        if not ids:
            return {}

        rows = self.db.execute(
            select(
                ClientRecord.id,
                LegalEntity.official_name,
                ClientRecord.office_client_number,
            )
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.id.in_(ids), ClientRecord.deleted_at.is_(None))
        ).all()
        return {
            row.id: ClientDisplayProfile(
                client_name=row.official_name,
                office_client_number=row.office_client_number,
            )
            for row in rows
        }
