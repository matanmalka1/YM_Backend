from __future__ import annotations

from datetime import timedelta
from random import Random

from sqlalchemy import select

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.clients.services.client_create_service import CreateClientService
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.notes.models.note_entity_note import EntityNote

from ..data.business_names import seed_business_name
from ..data.demo_catalog import (
    BUSINESS_CATALOG,
    BUSINESS_NOTES,
    ENTITY_NOTE_TEXTS,
    REALISTIC_ADDRESSES,
    demo_email,
    mobile_phone,
)
from ..data.random_utils import full_name, generate_valid_israeli_id
from .shared.client_refs import attach_seed_client_context


def create_clients(
    db,
    rng: Random,
    cfg,
    users=None,
) -> list[tuple[ClientRecord, Business]]:
    """
    Create clients via the production CreateClientService.
    Returns list of (client_record, primary_business) pairs.
    Each call automatically triggers ClientOnboardingOrchestrator.
    """
    svc = CreateClientService(db)
    actor_id = users[0].id if users else None

    existing_max = db.execute(select(ClientRecord)).scalars().all()
    serial_offset = len(existing_max)

    results: list[tuple[ClientRecord, Business]] = []
    used_names: set[str] = set(db.execute(select(Business.business_name)).scalars().all())

    for i in range(cfg.clients):
        serial = serial_offset + i + 1
        entity_type = rng.choices(
            population=[
                EntityType.OSEK_MURSHE,
                EntityType.OSEK_PATUR,
                EntityType.COMPANY_LTD,
            ],
            weights=[55, 30, 15],
            k=1,
        )[0]
        address = rng.choice(REALISTIC_ADDRESSES)

        if entity_type == EntityType.COMPANY_LTD:
            full_name_value = BUSINESS_CATALOG[(serial - 1) % len(BUSINESS_CATALOG)]
            id_number_type = IdNumberType.CORPORATION
            id_number = generate_valid_israeli_id(serial, prefix="5")
            vat_reporting_frequency = rng.choices(
                population=[VatType.MONTHLY, VatType.BIMONTHLY],
                weights=[50, 50],
                k=1,
            )[0]
        else:
            full_name_value = full_name(rng)
            id_number_type = IdNumberType.INDIVIDUAL
            id_number = generate_valid_israeli_id(serial, prefix=str(rng.choice([0, 1, 2, 3])))
            if entity_type == EntityType.OSEK_PATUR:
                vat_reporting_frequency = VatType.EXEMPT
            else:
                vat_reporting_frequency = rng.choices(
                    population=[VatType.BIMONTHLY, VatType.MONTHLY],
                    weights=[70, 30],
                    k=1,
                )[0]

        advance_rate = round(rng.uniform(2.0, 12.0), 2)
        advance_payment_frequency = rng.choices(
            population=[
                AdvancePaymentFrequency.BIMONTHLY,
                AdvancePaymentFrequency.MONTHLY,
            ],
            weights=[75, 25],
            k=1,
        )[0]
        phone = mobile_phone(rng)
        email = demo_email("client", serial)

        business_name = seed_business_name(
            client_full_name=full_name_value,
            entity_type=entity_type,
            business_index=0,
            serial=serial,
            rng=rng,
            used_names=used_names,
        )
        open_days_ago = rng.randint(20, 1100)
        business_opened_at = cfg.reference_date - timedelta(days=open_days_ago)

        client_record, primary_business = svc.create_client(
            full_name=full_name_value,
            id_number=id_number,
            business_name=business_name,
            id_number_type=id_number_type,
            entity_type=entity_type,
            phone=phone,
            email=email,
            address_street=address["street"],
            address_building_number=str(rng.randint(1, 220)),
            address_apartment=str(rng.randint(1, 30)) if rng.random() < 0.75 else None,
            address_city=address["city"],
            address_zip_code=address["zip_code"],
            vat_reporting_frequency=vat_reporting_frequency,
            advance_payment_frequency=advance_payment_frequency,
            advance_rate=advance_rate,
            accountant_id=rng.choice(users).id if users else None,
            business_opened_at=business_opened_at,
            business_notes=rng.choice(BUSINESS_NOTES),
            actor_id=actor_id,
        )
        # Attach in-memory helpers used by demo builders for grouping.
        # These attributes do NOT exist on the ORM model — they are seed-only handles.
        attach_seed_client_context(primary_business, client_record)
        # Convenience attributes accessed by downstream builders (signature_requests, notifications)
        client_record.entity_type = entity_type  # type: ignore[attr-defined]
        client_record.full_name = full_name_value  # type: ignore[attr-defined]
        client_record.email = email  # type: ignore[attr-defined]
        client_record.phone = phone  # type: ignore[attr-defined]
        client_record.vat_reporting_frequency = vat_reporting_frequency  # type: ignore[attr-defined]
        client_record.advance_payment_frequency = advance_payment_frequency  # type: ignore[attr-defined]

        results.append((client_record, primary_business))
        db.flush()

    return results


def create_extra_businesses(
    db,
    rng: Random,
    cfg,
    client_pairs: list[tuple[ClientRecord, Business]],
    users=None,
) -> list[Business]:
    """
    Add extra businesses for ~20% of clients (multi-business scenario).
    These are additional businesses beyond the primary one created during onboarding.
    """
    from app.businesses.services.business_service import BusinessService

    biz_svc = BusinessService(db)
    actor_id = users[0].id if users else None
    extra: list[Business] = []
    used_names: set[str] = set(db.execute(select(Business.business_name)).scalars().all())

    multi_target = max(1, round(len(client_pairs) * 0.2))
    multi_clients = {
        cr.id for cr, _ in rng.sample(client_pairs, k=min(multi_target, len(client_pairs)))
    }

    serial = 10000
    for client_record, primary_business in client_pairs:
        if client_record.id not in multi_clients:
            continue
        if getattr(client_record, "entity_type", None) == EntityType.EMPLOYEE:
            continue

        count = rng.randint(1, 2)
        for business_index in range(1, count + 1):
            serial += 1
            entity_type = getattr(client_record, "entity_type", None)
            biz_name = seed_business_name(
                client_full_name=getattr(client_record, "full_name", str(client_record.id)),
                entity_type=entity_type,
                business_index=business_index,
                serial=serial,
                rng=rng,
                used_names=used_names,
            )
            opened_at = (
                primary_business.opened_at - timedelta(days=rng.randint(0, 180))
                if hasattr(primary_business, "opened_at") and primary_business.opened_at
                else None
            )

            biz = biz_svc.create_business_for_client_record(
                client_record_id=client_record.id,
                opened_at=opened_at,
                business_name=biz_name,
                notes=rng.choice(BUSINESS_NOTES),
                actor_id=actor_id,
            )
            attach_seed_client_context(biz, client_record)
            extra.append(biz)
            db.flush()

    return extra


def create_entity_notes(db, rng: Random, clients: list[ClientRecord], users) -> None:
    sample = rng.sample(clients, min(len(clients), max(1, len(clients) // 2)))
    for client in sample:
        db.add(
            EntityNote(
                entity_type="client",
                entity_id=client.id,
                note=rng.choice(ENTITY_NOTE_TEXTS),
                created_by=rng.choice(users).id if users else None,
            )
        )
    db.flush()
