from sqlalchemy.orm import Session

from app.businesses.models.business import Business
from app.legal_entities.models.person_legal_entity_link import PersonLegalEntityRole


class BusinessContactService:
    def __init__(self, db: Session):
        self.db = db

    def contact_email(self, business: Business) -> str | None:
        if business.email_override:
            return business.email_override
        owner = self._owner_person(business)
        return owner.email if owner else None

    def contact_phone(self, business: Business) -> str | None:
        if business.phone_override:
            return business.phone_override
        owner = self._owner_person(business)
        return owner.phone if owner else None

    def display_name(self, business: Business) -> str:
        if business.business_name:
            return business.business_name
        if business.legal_entity:
            return business.legal_entity.official_name
        return ""

    def _owner_person(self, business: Business):
        if not business.legal_entity:
            return None
        for link in business.legal_entity.person_links:
            if link.role == PersonLegalEntityRole.OWNER:
                return link.person
        return None
