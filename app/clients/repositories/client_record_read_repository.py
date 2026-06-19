from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)


class ClientRecordData(TypedDict):
    id: int
    full_name: str | None
    id_number: str
    id_number_type: IdNumberType | None
    entity_type: EntityType | None
    status: ClientStatus
    office_client_number: int | None
    accountant_id: int | None
    notes: str | None
    vat_reporting_frequency: VatType | None
    advance_payment_frequency: AdvancePaymentFrequency | None
    vat_exempt_ceiling: Decimal | None
    advance_rate: Decimal | None
    advance_rate_updated_at: date | None
    annual_revenue: Decimal | None
    phone: str | None
    email: str | None
    address_street: str | None
    address_building_number: str | None
    address_apartment: str | None
    address_city: str | None
    address_zip_code: str | None
    created_at: datetime
    updated_at: datetime | None
    created_by: int | None
    deleted_at: datetime | None
    deleted_by: int | None
    restored_at: datetime | None
    restored_by: int | None


def _full_record_query():
    return (
        select(ClientRecord, LegalEntity, Person)
        .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
        .outerjoin(
            PersonLegalEntityLink,
            (PersonLegalEntityLink.legal_entity_id == LegalEntity.id)
            & (PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER),
        )
        .outerjoin(Person, Person.id == PersonLegalEntityLink.person_id)
    )


def _full_record_dict(cr: ClientRecord, le: LegalEntity, person: Person | None) -> ClientRecordData:
    full_name = person.full_name if person and person.full_name else le.official_name
    return {
        "id": cr.id,
        "full_name": full_name,
        "id_number": le.id_number,
        "id_number_type": le.id_number_type,
        "entity_type": le.entity_type,
        "status": cr.status,
        "office_client_number": cr.office_client_number,
        "accountant_id": cr.accountant_id,
        "notes": cr.notes,
        "vat_reporting_frequency": le.vat_reporting_frequency,
        "advance_payment_frequency": le.advance_payment_frequency,
        "vat_exempt_ceiling": le.vat_exempt_ceiling,
        "advance_rate": le.advance_rate,
        "advance_rate_updated_at": le.advance_rate_updated_at,
        "annual_revenue": le.annual_revenue,
        "phone": person.phone if person else None,
        "email": person.email if person else None,
        "address_street": person.address_street if person else None,
        "address_building_number": person.address_building_number if person else None,
        "address_apartment": person.address_apartment if person else None,
        "address_city": person.address_city if person else None,
        "address_zip_code": person.address_zip_code if person else None,
        "created_at": cr.created_at,
        "updated_at": cr.updated_at,
        "created_by": cr.created_by,
        "deleted_at": cr.deleted_at,
        "deleted_by": cr.deleted_by,
        "restored_at": cr.restored_at,
        "restored_by": cr.restored_by,
    }


def get_full_record(db: Session, client_record_id: int) -> ClientRecordData | None:
    row = db.execute(
        _full_record_query().where(
            ClientRecord.id == client_record_id, ClientRecord.deleted_at.is_(None)
        )
    ).first()
    return _full_record_dict(*row) if row else None


def get_full_record_including_deleted(
    db: Session, client_record_id: int
) -> ClientRecordData | None:
    row = db.execute(_full_record_query().where(ClientRecord.id == client_record_id)).first()
    return _full_record_dict(*row) if row else None


def get_full_records_bulk(db: Session, client_record_ids: list[int]) -> dict[int, ClientRecordData]:
    if not client_record_ids:
        return {}
    rows = db.execute(
        _full_record_query().where(
            ClientRecord.id.in_(client_record_ids),
            ClientRecord.deleted_at.is_(None),
        )
    ).all()
    return {cr.id: _full_record_dict(cr, le, person) for cr, le, person in rows}
