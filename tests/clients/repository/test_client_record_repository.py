"""Tests for ClientRecordRepository — Fix 1 lookup chain."""

from datetime import date

import pytest

from app.businesses.business_guards import (
    assert_business_belongs_to_legal_entity,
)
from app.businesses.models.business import Business, BusinessStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import IdNumberType
from app.core.exceptions import NotFoundError
from tests.helpers.identity import SeededClient


def _seed(client_factory, *, id_number="LE-TEST-001") -> SeededClient:
    return client_factory(
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        full_name="Test Entity",
        create_person=False,
        commit=True,
    )


# ── Direct client-record lookups ─────────────────────────────────────────────


def test_get_by_id_returns_record(test_db, client_factory):
    client = _seed(client_factory)
    repo = ClientRecordRepository(test_db)
    result = repo.get_by_id(client.id)
    assert result is not None
    assert result.legal_entity_id == client.legal_entity_id


def test_get_by_id_returns_none_for_unknown(test_db):
    repo = ClientRecordRepository(test_db)
    assert repo.get_by_id(999999) is None


def test_get_legal_entity_id_by_client_record_id_returns_id(test_db, client_factory):
    client = _seed(client_factory, id_number="LE-TEST-002")
    repo = ClientRecordRepository(test_db)
    result = repo.get_legal_entity_id_by_client_record_id(client.id)
    assert result == client.legal_entity_id


def test_get_legal_entity_id_by_client_record_id_raises_for_unknown(test_db):
    repo = ClientRecordRepository(test_db)
    with pytest.raises(NotFoundError) as exc:
        repo.get_legal_entity_id_by_client_record_id(999999)
    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


# ── Fix 2: guard assert_business_belongs_to_legal_entity end-to-end ──────────


def _seed_business_with_legal_entity(
    create_client_with_business, id_number="LE-BIZ-001"
) -> tuple[SeededClient, Business]:
    client, business = create_client_with_business(
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        full_name="Test Entity",
        business_name="Guard Test Biz",
        opened_at=date(2026, 1, 1),
        business_status=BusinessStatus.ACTIVE,
        create_person=False,
    )
    return client, business


def test_assert_business_belongs_to_legal_entity_passes_on_match(create_client_with_business):
    client, biz = _seed_business_with_legal_entity(create_client_with_business)
    # Must not raise
    assert_business_belongs_to_legal_entity(biz, client.legal_entity_id)


def test_assert_business_belongs_to_legal_entity_raises_on_mismatch(create_client_with_business):
    _, biz = _seed_business_with_legal_entity(create_client_with_business, id_number="LE-BIZ-002")
    with pytest.raises(NotFoundError) as exc:
        assert_business_belongs_to_legal_entity(biz, 999999)
    assert exc.value.code == "BUSINESS.NOT_FOUND"


# ── Fix 2: BusinessService.update_business uses client-record lookup path ────


def test_update_business_via_legal_entity_id(test_db, create_client_with_business, actor_user):
    """Confirms the lookup chain: client_id → ClientRecord → legal_entity_id → guard passes."""
    from app.businesses.services.business_service import BusinessService
    from app.users.models.user import UserRole

    client, biz = _seed_business_with_legal_entity(
        create_client_with_business, id_number="LE-UPD-001"
    )

    service = BusinessService(test_db)
    updated = service.update_business(
        biz.id,
        client_id=client.id,
        user_role=UserRole.ADVISOR,
        business_name="Updated Name",
        actor_id=actor_user.id,
    )
    assert updated.business_name == "Updated Name"


# ── Fix 4: correspondence ownership now raises NotFoundError ─────────────────


def test_correspondence_ownership_raises_not_found_error(
    test_db, client_factory, create_client_with_business
):
    from app.communications.services.correspondence_service import CorrespondenceService

    _, biz = create_client_with_business(
        id_number="CORR-A",
        id_number_type=IdNumberType.OTHER,
        full_name="Client A",
        business_name="Biz A",
        opened_at=date(2026, 1, 1),
        business_status=BusinessStatus.ACTIVE,
        create_person=False,
    )
    client_b = client_factory(
        id_number="CORR-B",
        id_number_type=IdNumberType.OTHER,
        full_name="Client B",
        office_client_number=100802,
        create_person=False,
        commit=True,
    )

    service = CorrespondenceService(test_db)
    with pytest.raises(NotFoundError) as exc:
        service._assert_business_belongs_to_client(biz.id, client_b.id)
    assert exc.value.code == "BUSINESS.NOT_FOUND"
