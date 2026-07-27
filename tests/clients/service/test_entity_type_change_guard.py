from datetime import date
from itertools import count

import pytest
from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_ENTITY_TYPE_CHANGED,
    ENTITY_CLIENT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.clients.models.client_record import ClientRecord
from app.clients.services.client_update_service import ClientUpdateService
from app.common.enums import EntityType, IdNumberType, VatType
from app.core.exceptions import ForbiddenError
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import UserRole

_seq = count(1)


def _setup(test_db, client_factory, business_factory, user_factory) -> tuple:
    """Returns (client_record, advisor_user, secretary_user)."""
    idx = next(_seq)
    seeded = client_factory(
        full_name=f"EntityType Guard {idx}",
        id_number=f"ET{idx:06d}",
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    cr = test_db.scalars(select(ClientRecord).filter(ClientRecord.id == seeded.id)).one()

    business_factory(
        legal_entity_id=seeded.legal_entity_id,
        business_name=seeded.full_name,
        opened_at=date(2026, 1, 1),
    )

    advisor = user_factory(role=UserRole.ADVISOR, commit=False)
    secretary = user_factory(role=UserRole.SECRETARY, commit=False)
    test_db.commit()
    test_db.refresh(cr)
    return cr, advisor, secretary


def test_secretary_cannot_change_entity_type(
    test_db, client_factory, business_factory, user_factory
):
    cr, advisor, secretary = _setup(test_db, client_factory, business_factory, user_factory)
    service = ClientUpdateService(test_db)

    with pytest.raises(ForbiddenError):
        service.update_client(
            cr.id,
            actor_id=secretary.id,
            actor_role=UserRole.SECRETARY,
            entity_type=EntityType.COMPANY_LTD,
        )


def test_advisor_can_change_entity_type(test_db, client_factory, business_factory, user_factory):
    cr, advisor, secretary = _setup(test_db, client_factory, business_factory, user_factory)

    service = ClientUpdateService(test_db)
    service.update_client(
        cr.id,
        actor_id=advisor.id,
        actor_role=UserRole.ADVISOR,
        entity_type=EntityType.COMPANY_LTD,
    )

    test_db.refresh(cr)
    le = test_db.scalars(select(LegalEntity).filter(LegalEntity.id == cr.legal_entity_id)).one()
    assert le.entity_type == EntityType.COMPANY_LTD


def test_entity_type_change_logs_audit_entry(
    test_db, client_factory, business_factory, user_factory
):
    cr, advisor, secretary = _setup(test_db, client_factory, business_factory, user_factory)

    service = ClientUpdateService(test_db)
    service.update_client(
        cr.id,
        actor_id=advisor.id,
        actor_role=UserRole.ADVISOR,
        entity_type=EntityType.COMPANY_LTD,
    )

    matching_entries = test_db.scalars(
        select(EntityAuditLog).filter(
            EntityAuditLog.entity_type == ENTITY_CLIENT,
            EntityAuditLog.entity_id == cr.id,
            EntityAuditLog.action == ACTION_ENTITY_TYPE_CHANGED,
        )
    ).all()
    assert len(matching_entries) == 1
    entry = matching_entries[0]
    assert entry.old_value == {"entity_type": EntityType.OSEK_MURSHE.value}
    assert entry.new_value == {"entity_type": EntityType.COMPANY_LTD.value}
