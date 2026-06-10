from __future__ import annotations

from app.authority_contacts.models.authority_contact import ContactType

AUTHORITY_CONTACT_TYPES = [
    ContactType.ASSESSING_OFFICER,
    ContactType.VAT_BRANCH,
    ContactType.NATIONAL_INSURANCE,
]


def authority_contact_type(index: int) -> ContactType:
    return AUTHORITY_CONTACT_TYPES[index % len(AUTHORITY_CONTACT_TYPES)]


def authority_office_name(contact_type: ContactType, city: str | None) -> str:
    office_city = city or "תל אביב-יפו"
    if contact_type == ContactType.ASSESSING_OFFICER:
        return f"פקיד שומה {office_city}"
    if contact_type == ContactType.VAT_BRANCH:
        return f'משרד מע"מ {office_city}'
    if contact_type == ContactType.NATIONAL_INSURANCE:
        return f"ביטוח לאומי {office_city}"
    return f"רשות {office_city}"
