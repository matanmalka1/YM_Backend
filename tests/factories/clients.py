from __future__ import annotations

from datetime import date, datetime
from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.businesses.models.business import Business, BusinessStatus
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import (
    IdNumberType,
)
from app.legal_entities.models.legal_entity import LegalEntity
from tests.helpers.identity import (
    SeededClient,
    seed_business,
    seed_client_identity,
    seed_client_with_business,
)

# ClientRecord-level fields ClientFactory can still honour when it reuses an existing
# LegalEntity. Anything else in **client_fields targets LegalEntity/Person, which are not
# rewritten in that branch.

_EXISTING_ENTITY_CLIENT_FIELDS = frozenset(
    {
        "client_record_id",
        "office_client_number",
        "accountant_id",
        "status",
        "notes",
        "created_by",
        "deleted_at",
    }
)


class ClientFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        full_name: str | None = None,
        id_number: str | None = None,
        legal_entity_id: int | None = None,
        commit: bool = False,
        **client_fields: Any,
    ) -> SeededClient:
        sequence = next(self._sequence)
        if legal_entity_id is None:
            client = seed_client_identity(
                self.db,
                full_name=full_name or f"Test Client {sequence}",
                id_number=id_number or f"TEST-CLIENT-{sequence:06d}",
                **client_fields,
            )
        else:
            unsupported = set(client_fields) - _EXISTING_ENTITY_CLIENT_FIELDS
            if unsupported:
                raise ValueError(
                    "These fields belong to LegalEntity/Person and are ignored when "
                    f"legal_entity_id is passed: {sorted(unsupported)}"
                )
            legal_entity = self.db.get(LegalEntity, legal_entity_id)
            if legal_entity is None:
                raise ValueError(f"LegalEntity id={legal_entity_id} does not exist")
            person = legal_entity.person_links[0].person if legal_entity.person_links else None
            record = ClientRecord(
                id=client_fields.get("client_record_id"),
                legal_entity_id=legal_entity.id,
                office_client_number=client_fields.get("office_client_number"),
                accountant_id=client_fields.get("accountant_id"),
                status=client_fields.get("status", ClientStatus.ACTIVE),
                notes=client_fields.get("notes"),
                created_by=client_fields.get("created_by"),
                deleted_at=client_fields.get("deleted_at"),
            )
            self.db.add(record)
            self.db.flush()
            client = SeededClient(
                id=record.id,
                legal_entity_id=legal_entity.id,
                full_name=legal_entity.official_name,
                id_number=legal_entity.id_number,
                id_number_type=legal_entity.id_number_type,
                entity_type=legal_entity.entity_type,
                phone=getattr(person, "phone", None),
                email=getattr(person, "email", None),
                address_street=getattr(person, "address_street", None),
                address_building_number=getattr(person, "address_building_number", None),
                address_apartment=getattr(person, "address_apartment", None),
                address_city=getattr(person, "address_city", None),
                address_zip_code=getattr(person, "address_zip_code", None),
                office_client_number=record.office_client_number,
                notes=record.notes,
                vat_reporting_frequency=legal_entity.vat_reporting_frequency,
                vat_exempt_ceiling=legal_entity.vat_exempt_ceiling,
                advance_rate=legal_entity.advance_rate,
                advance_rate_updated_at=legal_entity.advance_rate_updated_at,
                accountant_id=record.accountant_id,
                status=record.status,
                created_by=record.created_by,
                deleted_at=record.deleted_at,
            )
        if commit:
            self.db.commit()
        return client


class BusinessFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        legal_entity_id: int,
        business_name: str | None = None,
        opened_at: date | None = None,
        status: BusinessStatus = BusinessStatus.ACTIVE,
        created_by: int | None = None,
        notes: str | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> Business:
        sequence = next(self._sequence)
        business = seed_business(
            self.db,
            legal_entity_id=legal_entity_id,
            business_name=business_name or f"Test Business {sequence}",
            opened_at=opened_at,
            status=status,
            created_by=created_by,
            notes=notes,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
        )
        if commit:
            self.db.commit()
            self.db.refresh(business)
        return business


class ClientBusinessFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        full_name: str | None = None,
        id_number: str | None = None,
        business_name: str | None = None,
        id_number_type: IdNumberType = IdNumberType.INDIVIDUAL,
        opened_at: date | None = None,
        business_status: BusinessStatus = BusinessStatus.ACTIVE,
        business_created_by: int | None = None,
        business_notes: str | None = None,
        commit: bool = False,
        **client_fields: Any,
    ) -> tuple[SeededClient, Business]:
        sequence = next(self._sequence)
        resolved_name = full_name or f"Test Client {sequence}"
        client, business = seed_client_with_business(
            self.db,
            full_name=resolved_name,
            id_number=id_number or f"TEST-BUSINESS-CLIENT-{sequence:06d}",
            business_name=business_name,
            id_number_type=id_number_type,
            opened_at=opened_at,
            business_status=business_status,
            business_created_by=business_created_by,
            business_notes=business_notes,
            **client_fields,
        )
        if commit:
            self.db.commit()
            self.db.refresh(business)
        return client, business
