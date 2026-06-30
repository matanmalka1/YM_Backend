from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.businesses.models.business import Business, BusinessStatus
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)


@dataclass
class SeededClient:
    id: int
    legal_entity_id: int
    full_name: str
    id_number: str
    id_number_type: IdNumberType
    entity_type: EntityType | None
    phone: str | None
    email: str | None
    address_street: str | None
    address_building_number: str | None
    address_apartment: str | None
    address_city: str | None
    address_zip_code: str | None
    office_client_number: int | None
    notes: str | None
    vat_reporting_frequency: VatType | None
    vat_exempt_ceiling: object | None
    advance_rate: object | None
    advance_rate_updated_at: date | None
    accountant_id: int | None
    status: ClientStatus
    created_by: int | None
    deleted_at: object | None


def seed_client_identity(
    db: Session,
    *,
    full_name: str,
    id_number: str,
    id_number_type: IdNumberType = IdNumberType.INDIVIDUAL,
    entity_type: EntityType | None = None,
    phone: str | None = None,
    email: str | None = None,
    address_street: str | None = None,
    address_building_number: str | None = None,
    address_apartment: str | None = None,
    address_city: str | None = None,
    address_zip_code: str | None = None,
    office_client_number: int | None = None,
    notes: str | None = None,
    vat_reporting_frequency: VatType | None = None,
    advance_payment_frequency: AdvancePaymentFrequency | None = None,
    vat_exempt_ceiling=None,
    advance_rate=None,
    advance_rate_updated_at: date | None = None,
    accountant_id: int | None = None,
    status: ClientStatus = ClientStatus.ACTIVE,
    created_by: int | None = None,
    deleted_at=None,
    create_person: bool = True,
    client_record_id: int | None = None,
) -> SeededClient:
    legal_entity = LegalEntity(
        id_number=id_number,
        id_number_type=id_number_type,
        entity_type=entity_type,
        official_name=full_name,
        vat_reporting_frequency=vat_reporting_frequency,
        advance_payment_frequency=advance_payment_frequency,
        vat_exempt_ceiling=vat_exempt_ceiling,
        advance_rate=advance_rate,
        advance_rate_updated_at=advance_rate_updated_at,
    )
    db.add(legal_entity)
    db.flush()

    if create_person:
        person_type = (
            IdNumberType.OTHER if id_number_type == IdNumberType.CORPORATION else id_number_type
        )
        person = Person(
            full_name=full_name,
            id_number=id_number,
            id_number_type=person_type,
            phone=phone,
            email=email,
            address_street=address_street,
            address_building_number=address_building_number,
            address_apartment=address_apartment,
            address_city=address_city,
            address_zip_code=address_zip_code,
        )
        db.add(person)
        db.flush()
        db.add(
            PersonLegalEntityLink(
                person_id=person.id,
                legal_entity_id=legal_entity.id,
                role=PersonLegalEntityRole.OWNER,
            )
        )
        db.flush()

    record = ClientRecord(
        id=client_record_id,
        legal_entity_id=legal_entity.id,
        office_client_number=office_client_number,
        accountant_id=accountant_id,
        status=status,
        notes=notes,
        created_by=created_by,
        deleted_at=deleted_at,
    )
    db.add(record)
    db.flush()

    return SeededClient(
        id=record.id,
        legal_entity_id=legal_entity.id,
        full_name=full_name,
        id_number=id_number,
        id_number_type=id_number_type,
        entity_type=entity_type,
        phone=phone,
        email=email,
        address_street=address_street,
        address_building_number=address_building_number,
        address_apartment=address_apartment,
        address_city=address_city,
        address_zip_code=address_zip_code,
        office_client_number=office_client_number,
        notes=notes,
        vat_reporting_frequency=vat_reporting_frequency,
        vat_exempt_ceiling=vat_exempt_ceiling,
        advance_rate=advance_rate,
        advance_rate_updated_at=advance_rate_updated_at,
        accountant_id=accountant_id,
        status=status,
        created_by=created_by,
        deleted_at=deleted_at,
    )


def seed_business(
    db: Session,
    *,
    legal_entity_id: int,
    business_name: str,
    opened_at: date | None = None,
    status: BusinessStatus = BusinessStatus.ACTIVE,
    created_by: int | None = None,
    notes: str | None = None,
) -> Business:
    business = Business(
        legal_entity_id=legal_entity_id,
        business_name=business_name,
        opened_at=opened_at or date.today(),
        status=status,
        created_by=created_by,
        notes=notes,
    )
    db.add(business)
    db.flush()
    return business


def seed_client_with_business(
    db: Session,
    *,
    full_name: str,
    id_number: str,
    business_name: str | None = None,
    id_number_type: IdNumberType = IdNumberType.INDIVIDUAL,
    opened_at: date | None = None,
    business_status: BusinessStatus = BusinessStatus.ACTIVE,
    business_created_by: int | None = None,
    business_notes: str | None = None,
    **client_fields,
) -> tuple[SeededClient, Business]:
    client = seed_client_identity(
        db,
        full_name=full_name,
        id_number=id_number,
        id_number_type=id_number_type,
        **client_fields,
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=business_name or full_name,
        opened_at=opened_at,
        status=business_status,
        created_by=business_created_by,
        notes=business_notes,
    )
    business.client_id = client.id
    business.client_record_id = client.id
    db.flush()
    return client, business
