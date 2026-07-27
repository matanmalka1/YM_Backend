from datetime import date

import pytest

from app.businesses.models.business import Business, BusinessStatus
from app.businesses.services.business_client_business_service import ClientBusinessService
from app.businesses.services.business_service import BusinessService
from app.businesses.services.business_status_card_service import StatusCardService
from app.core.exceptions import NotFoundError
from app.users.models.user import UserRole


def _seed_client_record(client_factory, suffix: str):
    return client_factory(
        full_name=f"Entity {suffix}",
        id_number=f"LE-{suffix}",
    )


def _seed_business(business_factory, legal_entity_id: int) -> Business:
    return business_factory(
        legal_entity_id=legal_entity_id,
        business_name="Original Name",
        opened_at=date(2026, 1, 1),
        status=BusinessStatus.ACTIVE,
        commit=True,
    )


def test_update_business_resolves_legal_entity_from_client_record(
    test_db, client_factory, business_factory, actor_user
):
    client_record = _seed_client_record(client_factory, "UPD")
    business = _seed_business(business_factory, client_record.legal_entity_id)

    updated = BusinessService(test_db).update_business(
        business_id=business.id,
        client_id=client_record.id,
        user_role=UserRole.ADVISOR,
        business_name="Updated Name",
        actor_id=actor_user.id,
    )

    assert updated.business_name == "Updated Name"


def test_status_card_raises_when_client_record_missing(test_db):
    with pytest.raises(NotFoundError) as exc:
        StatusCardService(test_db).get_status_card(999999)

    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_client_business_service_uses_client_record_legal_entity(
    test_db, client_factory, business_factory
):
    owner = _seed_client_record(client_factory, "OWNER")
    other = _seed_client_record(client_factory, "OTHER")
    business = _seed_business(business_factory, owner.legal_entity_id)

    service = ClientBusinessService(test_db)
    assert service.get_for_client(owner.id, business.id).id == business.id

    with pytest.raises(NotFoundError) as exc:
        service.get_for_client(other.id, business.id)

    assert exc.value.code == "BUSINESS.NOT_FOUND"
