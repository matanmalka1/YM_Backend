from sqlalchemy import select

from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)
from app.clients.services.create_client_service import create_client_identity_only
from app.common.enums import EntityType, IdNumberType


def test_create_client_creates_identity_graph(test_db):
    client_record = create_client_identity_only(
        test_db,
        full_name="Client Identity",
        id_number="123456780",
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=EntityType.OSEK_MURSHE,
        phone="0501234567",
        email="client@example.com",
        address_city="תל אביב",
        accountant_id=1,
        actor_id=7,
    )

    person = test_db.scalars(select(Person).filter(Person.id_number == "123456780")).one()
    legal_entity = test_db.scalars(
        select(LegalEntity).filter(LegalEntity.id == client_record.legal_entity_id)
    ).one()
    link = test_db.scalars(
        select(PersonLegalEntityLink).filter(
            PersonLegalEntityLink.person_id == person.id,
            PersonLegalEntityLink.legal_entity_id == legal_entity.id,
        )
    ).one()
    stored_record = test_db.scalars(
        select(ClientRecord).filter(ClientRecord.id == client_record.id)
    ).one()

    assert stored_record.id == client_record.id
    assert stored_record.office_client_number == client_record.office_client_number
    assert stored_record.accountant_id == 1
    assert legal_entity.id_number == "123456780"
    assert legal_entity.official_name == "Client Identity"
    assert person.full_name == "Client Identity"
    assert person.phone == "0501234567"
    assert person.email == "client@example.com"
    assert person.address_city == "תל אביב"
    assert link.role == PersonLegalEntityRole.OWNER
