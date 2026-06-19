"""Shared helpers for task service tests."""

from __future__ import annotations

from datetime import date
from itertools import count

from app.businesses.models.business import Business, BusinessStatus
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity

_seq = count(1)


def create_business(db):
    """Create a minimal active business with a linked ClientRecord for task tests."""
    idx = next(_seq)
    le = LegalEntity(
        official_name=f"Task Test Client {idx}",
        id_number=f"T{idx:07d}",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    db.add(le)
    db.flush()

    cr = ClientRecord(
        legal_entity_id=le.id,
        status=ClientStatus.ACTIVE,
    )
    db.add(cr)
    db.flush()
    cr.office_client_number = 100000 + cr.id

    biz = Business(
        legal_entity_id=le.id,
        business_name=f"Task Biz {idx}",
        status=BusinessStatus.ACTIVE,
        opened_at=date.today(),
    )
    db.add(biz)
    db.flush()
    biz.client_id = cr.id  # type: ignore[attr-defined]
    return biz


def create_charge(db, client_record_id: int, business_id: int) -> Charge:
    charge = Charge(
        client_record_id=client_record_id,
        business_id=business_id,
        amount=100,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today(),
    )
    db.add(charge)
    db.commit()
    return charge
