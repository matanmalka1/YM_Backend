from datetime import date

import pytest

from app.businesses.models.business import Business, BusinessStatus
from app.businesses.services.business_client_business_service import ClientBusinessService
from app.businesses.services.business_service import BusinessService
from app.businesses.services.business_status_card_service import StatusCardService
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType
from app.core.exceptions import NotFoundError
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import UserRole


def _seed_client_record(test_db, suffix: str) -> ClientRecord:
    legal_entity = LegalEntity(
        id_number=f"LE-{suffix}",
        id_number_type=IdNumberType.INDIVIDUAL,
        official_name=f"Entity {suffix}",
    )
    test_db.add(legal_entity)
    test_db.flush()

    client_record = ClientRecord(legal_entity_id=legal_entity.id)
    test_db.add(client_record)
    test_db.flush()
    return client_record


def _seed_business(test_db, legal_entity_id: int) -> Business:
    business = Business(
        legal_entity_id=legal_entity_id,
        business_name="Original Name",
        opened_at=date(2026, 1, 1),
        status=BusinessStatus.ACTIVE,
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business


def test_update_business_resolves_legal_entity_from_client_record(test_db):
    client_record = _seed_client_record(test_db, "UPD")
    business = _seed_business(test_db, client_record.legal_entity_id)

    updated = BusinessService(test_db).update_business(
        business_id=business.id,
        client_id=client_record.id,
        user_role=UserRole.ADVISOR,
        business_name="Updated Name",
    )

    assert updated.business_name == "Updated Name"


def test_status_card_raises_when_client_record_missing(test_db):
    with pytest.raises(NotFoundError) as exc:
        StatusCardService(test_db).get_status_card(999999)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_client_business_service_uses_client_record_legal_entity(test_db):
    owner = _seed_client_record(test_db, "OWNER")
    other = _seed_client_record(test_db, "OTHER")
    business = _seed_business(test_db, owner.legal_entity_id)

    service = ClientBusinessService(test_db)
    assert service.get_for_client(owner.id, business.id).id == business.id

    with pytest.raises(NotFoundError) as exc:
        service.get_for_client(other.id, business.id)

    assert exc.value.code == "BUSINESS.NOT_FOUND"
