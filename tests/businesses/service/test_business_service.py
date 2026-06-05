from datetime import date
from types import SimpleNamespace

import pytest

from app.businesses.models.business import Business, BusinessStatus
from app.businesses.services.business_service import BusinessService
from app.core.exceptions import ConflictError, ForbiddenError
from app.users.models.user import UserRole
from tests.helpers.identity import seed_client_identity


def _create_business_row(
    test_db,
    *,
    status: BusinessStatus = BusinessStatus.ACTIVE,
    legal_entity_id: int | None = None,
) -> Business:
    business = Business(
        business_name="Service Test Business",
        opened_at=date(2026, 1, 1),
        status=status,
        legal_entity_id=legal_entity_id,
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business


def test_create_business_rejects_duplicate_name_for_client(test_db):
    service = BusinessService(test_db)
    service.client_repo = SimpleNamespace(
        get_by_id=lambda _client_id: SimpleNamespace(legal_entity_id=10)
    )
    service.business_repo = SimpleNamespace(
        all_non_deleted_are_closed_for_legal_entity=lambda _legal_entity_id: False,
        list_by_legal_entity=lambda _legal_entity_id, **_kwargs: [
            SimpleNamespace(business_name="Dup Name")
        ],
    )

    with pytest.raises(ConflictError) as exc:
        service.create_business(
            client_id=1,
            opened_at=date(2026, 1, 1),
            business_name="Dup Name",
        )

    assert exc.value.code == "BUSINESS.NAME_CONFLICT"


def test_update_business_blocks_non_advisor_freeze_or_close(test_db):
    client = seed_client_identity(test_db, full_name="Service Client", id_number="BSRV001")
    business = _create_business_row(test_db, legal_entity_id=client.legal_entity_id)
    service = BusinessService(test_db)

    with pytest.raises(ForbiddenError) as exc:
        service.update_business(
            business_id=business.id,
            client_id=client.id,
            user_role=UserRole.SECRETARY,
            status=BusinessStatus.CLOSED.value,
        )

    assert exc.value.code == "BUSINESS.FORBIDDEN"


def test_update_business_sets_closed_at_for_close_action(test_db):
    client = seed_client_identity(test_db, full_name="Service Client", id_number="BSRV002")
    business = _create_business_row(test_db, legal_entity_id=client.legal_entity_id)
    service = BusinessService(test_db)

    result = service.update_business(
        business_id=business.id,
        client_id=client.id,
        user_role=UserRole.ADVISOR,
        status=BusinessStatus.CLOSED.value,
    )

    assert result.status == BusinessStatus.CLOSED
    assert isinstance(result.closed_at, date)
