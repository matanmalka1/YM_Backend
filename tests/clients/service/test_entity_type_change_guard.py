from datetime import date
from itertools import count

import pytest
from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_ENTITY_TYPE_CHANGED,
    ENTITY_CLIENT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.clients.services.client_update_service import ClientUpdateService
from app.common.enums import EntityType, IdNumberType, VatType
from app.core.exceptions import ForbiddenError
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from tests.helpers.identity import seed_client_identity

_seq = count(1)


def _make_user(db, role=UserRole.ADVISOR) -> User:
    u = User(
        full_name=f"User {next(_seq)}",
        email=f"u{next(_seq)}@test.com",
        password_hash=AuthService.hash_password("x"),
        role=role,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def _setup(db) -> tuple:
    """Returns (client_record, advisor_user, secretary_user)."""
    idx = next(_seq)
    seeded = seed_client_identity(
        db,
        full_name=f"EntityType Guard {idx}",
        id_number=f"ET{idx:06d}",
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.MONTHLY,
    )
    cr = db.scalars(select(ClientRecord).filter(ClientRecord.id == seeded.id)).one()
    le = db.scalars(select(LegalEntity).filter(LegalEntity.id == seeded.legal_entity_id)).one()

    biz = Business(
        legal_entity_id=le.id,
        business_name=seeded.full_name,
        opened_at=date(2026, 1, 1),
    )
    db.add(biz)
    db.commit()
    db.refresh(cr)

    advisor = _make_user(db, UserRole.ADVISOR)
    secretary = _make_user(db, UserRole.SECRETARY)
    db.commit()
    return cr, advisor, secretary


def test_secretary_cannot_change_entity_type(test_db):
    cr, advisor, secretary = _setup(test_db)
    service = ClientUpdateService(test_db)

    with pytest.raises(ForbiddenError):
        service.update_client(
            cr.id,
            actor_id=secretary.id,
            actor_role=UserRole.SECRETARY,
            entity_type=EntityType.COMPANY_LTD,
        )


def test_advisor_can_change_entity_type(test_db):
    cr, advisor, secretary = _setup(test_db)

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


def test_entity_type_change_logs_audit_entry(test_db):
    cr, advisor, secretary = _setup(test_db)

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
