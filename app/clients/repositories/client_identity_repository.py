from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)


@dataclass(frozen=True, slots=True)
class ClientDisplayProfile:
    client_name: str
    office_client_number: int | None
    id_number: str


class ClientIdentityRepository(BaseRepository[ClientRecord]):
    model = ClientRecord

    def __init__(self, db: Session):
        super().__init__(db)

    def get_display_map(
        self,
        client_record_ids: Iterable[int],
        *,
        include_deleted: bool = False,
    ) -> dict[int, ClientDisplayProfile]:
        ids = list(set(client_record_ids))
        if not ids:
            return {}

        stmt = (
            select(
                ClientRecord.id,
                LegalEntity.official_name,
                ClientRecord.office_client_number,
                LegalEntity.id_number,
            )
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.id.in_(ids))
        )
        if not include_deleted:
            stmt = stmt.where(ClientRecord.deleted_at.is_(None))
        rows = self.db.execute(stmt).all()
        return {
            row.id: ClientDisplayProfile(
                client_name=row.official_name,
                office_client_number=row.office_client_number,
                id_number=row.id_number,
            )
            for row in rows
        }

    def get_owner_person(self, client_record_id: int) -> Person | None:
        """Return the OWNER Person for the client record, or None.

        First-row-wins on duplicate OWNER links (``.scalar()``), matching prior behavior.
        """
        return self.db.execute(
            select(Person)
            .select_from(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .outerjoin(
                PersonLegalEntityLink,
                (PersonLegalEntityLink.legal_entity_id == LegalEntity.id)
                & (PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER),
            )
            .outerjoin(Person, Person.id == PersonLegalEntityLink.person_id)
            .where(ClientRecord.id == client_record_id)
        ).scalar()

    def get_official_name(self, client_record_id: int) -> str | None:
        """Return the client's LegalEntity.official_name, or None."""
        return self.db.execute(
            select(LegalEntity.official_name)
            .join(ClientRecord, ClientRecord.legal_entity_id == LegalEntity.id)
            .where(ClientRecord.id == client_record_id)
        ).scalar()
