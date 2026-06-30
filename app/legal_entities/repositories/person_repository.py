from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import IdNumberType
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)


class PersonRepository(BaseRepository[Person]):
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        full_name: str,
        id_number: str,
        id_number_type: IdNumberType,
        phone: str | None = None,
        email: str | None = None,
        address_street: str | None = None,
        address_building_number: str | None = None,
        address_apartment: str | None = None,
        address_city: str | None = None,
        address_zip_code: str | None = None,
    ) -> Person:
        person = Person(
            full_name=full_name,
            id_number=id_number,
            id_number_type=id_number_type,
            phone=phone,
            email=email,
            address_street=address_street,
            address_building_number=address_building_number,
            address_apartment=address_apartment,
            address_city=address_city,
            address_zip_code=address_zip_code,
        )
        self.db.add(person)
        self.db.flush()
        return person

    def get_by_id_number(self, id_number_type: IdNumberType, id_number: str) -> Person | None:
        return self.db.scalars(
            select(Person).where(
                Person.id_number_type == id_number_type,
                Person.id_number == id_number,
            )
        ).first()

    def create_link(
        self,
        *,
        person_id: int,
        legal_entity_id: int,
        role: PersonLegalEntityRole = PersonLegalEntityRole.OWNER,
    ) -> PersonLegalEntityLink:
        link = PersonLegalEntityLink(
            person_id=person_id,
            legal_entity_id=legal_entity_id,
            role=role,
        )
        self.db.add(link)
        self.db.flush()
        return link

    def get_owner_for_legal_entity(self, legal_entity_id: int) -> Person | None:
        return self.db.scalars(
            select(Person)
            .join(PersonLegalEntityLink, PersonLegalEntityLink.person_id == Person.id)
            .where(
                PersonLegalEntityLink.legal_entity_id == legal_entity_id,
                PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER,
            )
        ).first()

    def ensure_owner(
        self,
        *,
        legal_entity_id: int,
        full_name: str,
        id_number: str,
        id_number_type: IdNumberType,
        **fields,
    ) -> tuple[Person, bool, PersonLegalEntityLink | None, bool]:
        owner_id_number_type = (
            IdNumberType.OTHER if id_number_type == IdNumberType.CORPORATION else id_number_type
        )
        person = self.get_by_id_number(owner_id_number_type, id_number)
        created_person = False
        if not person:
            person = self.create(
                full_name=full_name,
                id_number=id_number,
                id_number_type=owner_id_number_type,
                **fields,
            )
            created_person = True
        link = None
        created_link = False
        if not self.get_owner_for_legal_entity(legal_entity_id):
            link = self.create_link(person_id=person.id, legal_entity_id=legal_entity_id)
            created_link = True
        return person, created_person, link, created_link
