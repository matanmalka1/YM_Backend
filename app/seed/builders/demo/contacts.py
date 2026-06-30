from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random

from app.authority_contacts.models.authority_contact import AuthorityContact
from app.communications.models.correspondence import Correspondence, CorrespondenceType

from ...data.authority_offices import authority_contact_type, authority_office_name
from ...data.demo_catalog import (
    AUTHORITY_CONTACTS,
    CORRESPONDENCE_NOTES,
    CORRESPONDENCE_SUBJECTS,
    office_phone,
)
from ..shared.client_refs import attach_seed_client_context, get_seed_client_record_id


def create_authority_contacts(db, rng: Random, cfg, clients, businesses):
    contacts = []
    now = datetime.now(UTC)
    businesses_by_client: dict[int, list] = {}
    for business in businesses:
        businesses_by_client.setdefault(get_seed_client_record_id(business), []).append(business)

    for client in clients:
        if not businesses_by_client.get(client.id):
            continue
        num = rng.randint(
            cfg.min_authority_contacts_per_client, cfg.max_authority_contacts_per_client
        )
        for idx in range(num):
            created_at = now - timedelta(days=rng.randint(0, 300))
            updated_at = min(now, created_at + timedelta(days=rng.randint(0, 90)))
            contact_profile = AUTHORITY_CONTACTS[(client.id + idx - 1) % len(AUTHORITY_CONTACTS)]
            contact_type = authority_contact_type(idx)
            contact = AuthorityContact(
                client_record_id=client.id,
                contact_type=contact_type,
                name=contact_profile["name"],
                office=authority_office_name(contact_type, getattr(client, "city", None)),
                phone=office_phone(rng),
                email=contact_profile["email"],
                notes=rng.choice(
                    ["", "איש הקשר מטפל בתיק הפעיל", "מומלץ לתאם מראש לפני פנייה חוזרת"]
                ),
                created_at=created_at,
                updated_at=updated_at,
            )
            attach_seed_client_context(contact, client)
            db.add(contact)
            contacts.append(contact)
    db.flush()
    return contacts


def create_correspondence(db, rng: Random, businesses, users, authority_contacts):
    now = datetime.now(UTC)
    contacts_by_client: dict[int, list] = {}
    for contact in authority_contacts:
        contacts_by_client.setdefault(get_seed_client_record_id(contact), []).append(contact)

    for business in businesses:
        business_client_record_id = get_seed_client_record_id(business)
        for _ in range(rng.randint(1, 5)):
            occurred_at = now - timedelta(days=rng.randint(0, 120))
            candidate_contacts = contacts_by_client.get(business_client_record_id, [])
            contact = (
                rng.choice(candidate_contacts)
                if candidate_contacts and rng.random() < 0.65
                else None
            )
            db.add(
                Correspondence(
                    client_record_id=business_client_record_id,
                    business_id=business.id,
                    contact_id=contact.id if contact else None,
                    correspondence_type=rng.choice(list(CorrespondenceType)),
                    subject=rng.choice(CORRESPONDENCE_SUBJECTS),
                    notes=rng.choice(CORRESPONDENCE_NOTES),
                    occurred_at=occurred_at,
                    created_by=rng.choice(users).id,
                    created_at=occurred_at,
                )
            )
    db.flush()
