"""Tests for ClientRecordRepository — Fix 1 lookup chain."""

from datetime import date

import pytest

from app.businesses.models.business import Business, BusinessStatus
from app.businesses.services.business_guards import (
    assert_business_belongs_to_legal_entity,
)
from app.clients.models.client_record import ClientRecord
from app.clients.models.legal_entity import LegalEntity
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import IdNumberType
from app.core.exceptions import NotFoundError


def _seed(db, *, id_number="LE-TEST-001") -> tuple[LegalEntity, ClientRecord]:
    le = LegalEntity(
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        official_name="Test Entity",
    )
    db.add(le)
    db.flush()
    cr = ClientRecord(legal_entity_id=le.id)
    db.add(cr)
    db.commit()
    db.refresh(le)
    db.refresh(cr)
    return le, cr


# ── Direct client-record lookups ─────────────────────────────────────────────


def test_get_by_id_returns_record(test_db):
    le, cr = _seed(test_db)
    repo = ClientRecordRepository(test_db)
    result = repo.get_by_id(cr.id)
    assert result is not None
    assert result.legal_entity_id == le.id


def test_get_by_id_returns_none_for_unknown(test_db):
    repo = ClientRecordRepository(test_db)
    assert repo.get_by_id(999999) is None


def test_get_legal_entity_id_by_client_record_id_returns_id(test_db):
    le, cr = _seed(test_db, id_number="LE-TEST-002")
    repo = ClientRecordRepository(test_db)
    result = repo.get_legal_entity_id_by_client_record_id(cr.id)
    assert result == le.id


def test_get_legal_entity_id_by_client_record_id_raises_for_unknown(test_db):
    repo = ClientRecordRepository(test_db)
    with pytest.raises(NotFoundError) as exc:
        repo.get_legal_entity_id_by_client_record_id(999999)
    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


# ── Fix 2: guard assert_business_belongs_to_legal_entity end-to-end ──────────


def _seed_business_with_legal_entity(
    db, id_number="LE-BIZ-001"
) -> tuple[LegalEntity, ClientRecord, Business]:
    le = LegalEntity(
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        official_name="Test Entity",
    )
    db.add(le)
    db.flush()
    cr = ClientRecord(legal_entity_id=le.id)
    db.add(cr)
    db.flush()
    biz = Business(
        legal_entity_id=le.id,
        business_name="Guard Test Biz",
        opened_at=date(2026, 1, 1),
        status=BusinessStatus.ACTIVE,
    )
    db.add(biz)
    db.commit()
    db.refresh(le)
    db.refresh(cr)
    db.refresh(biz)
    return le, cr, biz


def test_assert_business_belongs_to_legal_entity_passes_on_match(test_db):
    le, _, biz = _seed_business_with_legal_entity(test_db)
    # Must not raise
    assert_business_belongs_to_legal_entity(biz, le.id)


def test_assert_business_belongs_to_legal_entity_raises_on_mismatch(test_db):
    _, _, biz = _seed_business_with_legal_entity(test_db, id_number="LE-BIZ-002")
    with pytest.raises(NotFoundError) as exc:
        assert_business_belongs_to_legal_entity(biz, 999999)
    assert exc.value.code == "BUSINESS.NOT_FOUND"


# ── Fix 2: BusinessService.update_business uses client-record lookup path ────


def test_update_business_via_legal_entity_id(test_db):
    """Confirms the lookup chain: client_id → ClientRecord → legal_entity_id → guard passes."""
    from app.businesses.services.business_service import BusinessService
    from app.users.models.user import UserRole

    le, cr, biz = _seed_business_with_legal_entity(test_db, id_number="LE-UPD-001")

    service = BusinessService(test_db)
    updated = service.update_business(
        biz.id,
        client_id=cr.id,
        user_role=UserRole.ADVISOR,
        business_name="Updated Name",
    )
    assert updated.business_name == "Updated Name"


# ── Fix 4: correspondence ownership now raises NotFoundError ─────────────────


def test_correspondence_ownership_raises_not_found_error(test_db):
    from app.communications.services.correspondence_service import CorrespondenceService

    le_a = LegalEntity(
        id_number="CORR-A", id_number_type=IdNumberType.OTHER, official_name="Client A"
    )
    le_b = LegalEntity(
        id_number="CORR-B", id_number_type=IdNumberType.OTHER, official_name="Client B"
    )
    test_db.add_all([le_a, le_b])
    test_db.flush()
    client_a = ClientRecord(legal_entity_id=le_a.id, office_client_number=100801)
    client_b = ClientRecord(legal_entity_id=le_b.id, office_client_number=100802)
    test_db.add_all([client_a, client_b])
    test_db.flush()
    biz = Business(
        legal_entity_id=le_a.id,
        business_name="Biz A",
        opened_at=date(2026, 1, 1),
        status=BusinessStatus.ACTIVE,
    )
    test_db.add(biz)
    test_db.commit()

    service = CorrespondenceService(test_db)
    with pytest.raises(NotFoundError) as exc:
        service._assert_business_belongs_to_client(biz.id, client_b.id)
    assert exc.value.code == "BUSINESS.NOT_FOUND"
