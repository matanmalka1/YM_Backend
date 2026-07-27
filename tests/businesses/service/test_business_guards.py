import pytest

from app.businesses.business_guards import (
    assert_business_allows_create,
    validate_business_for_create,
)
from app.businesses.models.business import Business, BusinessStatus
from app.core.exceptions import ForbiddenError, NotFoundError


class _Business:
    def __init__(self, status):
        self.status = status


def test_assert_business_allows_create_allows_active():
    assert_business_allows_create(_Business(BusinessStatus.ACTIVE))


def test_assert_business_allows_create_blocks_closed_and_frozen():
    with pytest.raises(ForbiddenError) as closed:
        assert_business_allows_create(_Business(BusinessStatus.CLOSED))
    assert closed.value.code == "BUSINESS.CLOSED"

    with pytest.raises(ForbiddenError) as frozen:
        assert_business_allows_create(_Business(BusinessStatus.FROZEN))
    assert frozen.value.code == "BUSINESS.FROZEN"


def _create_business(
    client_factory, business_factory, status: BusinessStatus = BusinessStatus.ACTIVE
) -> Business:
    from datetime import date

    client = client_factory(
        full_name="Business Guard Client",
        id_number=f"BG-{status.value}",
    )
    return business_factory(
        legal_entity_id=client.legal_entity_id,
        business_name="Business Guard Business",
        opened_at=date.today(),
        status=status,
        commit=True,
    )


def test_validate_business_for_create_returns_business(test_db, client_factory, business_factory):
    business = _create_business(client_factory, business_factory)
    validated = validate_business_for_create(test_db, business.id)
    assert validated.id == business.id


def test_validate_business_for_create_raises_not_found(test_db):
    with pytest.raises(NotFoundError) as exc:
        validate_business_for_create(test_db, 999999)
    assert exc.value.code == "BUSINESS.NOT_FOUND"


def test_validate_business_for_create_blocks_frozen(test_db, client_factory, business_factory):
    business = _create_business(client_factory, business_factory, status=BusinessStatus.FROZEN)
    with pytest.raises(ForbiddenError) as exc:
        validate_business_for_create(test_db, business.id)
    assert exc.value.code == "BUSINESS.FROZEN"
