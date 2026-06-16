from app.core.error_codes import ErrorCode
from sqlalchemy.orm import Session

from app.businesses.models.business import Business, BusinessStatus
from app.businesses.repositories.business_repository import BusinessRepository
from app.core.exceptions import ForbiddenError, NotFoundError


def get_business_or_raise(db: Session, business_id: int) -> Business:
    """Fetch a business or raise NotFoundError."""
    business = BusinessRepository(db).get_by_id(business_id)
    if not business:
        raise NotFoundError(f"עסק {business_id} לא נמצא", ErrorCode.BUSINESS_NOT_FOUND)
    return business


def assert_business_allows_create(business: Business) -> None:
    """Raise ForbiddenError if business status blocks new record creation."""
    if business.status == BusinessStatus.CLOSED:
        raise ForbiddenError(
            "עסק סגור — לא ניתן ליצור עבודה חדשה",
            ErrorCode.BUSINESS_CLOSED,
        )
    if business.status == BusinessStatus.FROZEN:
        raise ForbiddenError(
            "עסק מוקפא — לא ניתן ליצור עבודה חדשה",
            ErrorCode.BUSINESS_FROZEN,
        )


def validate_business_for_create(db: Session, business_id: int) -> Business:
    """Fetch business and assert it allows new record creation."""
    business = get_business_or_raise(db, business_id)
    assert_business_allows_create(business)
    return business


def assert_business_belongs_to_legal_entity(business: Business, legal_entity_id: int) -> None:
    """Raise NotFoundError if business.legal_entity_id does not match the given legal_entity_id."""
    if business.legal_entity_id != legal_entity_id:
        raise NotFoundError(
            f"עסק {business.id} לא נמצא",
            ErrorCode.BUSINESS_NOT_FOUND,
        )
