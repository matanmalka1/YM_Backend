from datetime import date

from sqlalchemy import select

from app.advance_payments.models.advance_payment import AdvancePayment
from app.clients.services.client_onboarding_service import (
    ClientOnboardingOrchestrator,
)
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from tests.helpers.identity import seed_client_identity


def _seed_client(
    db,
    *,
    name: str,
    id_number: str,
    entity_type: EntityType,
    vat_frequency: VatType,
    advance_frequency: AdvancePaymentFrequency,
):
    return seed_client_identity(
        db,
        full_name=name,
        id_number=id_number,
        id_number_type=(
            IdNumberType.CORPORATION
            if entity_type == EntityType.COMPANY_LTD
            else IdNumberType.INDIVIDUAL
        ),
        entity_type=entity_type,
        vat_reporting_frequency=vat_frequency,
        advance_payment_frequency=advance_frequency,
        office_client_number=int(id_number[-6:]),
    )


def _run_onboarding(db, actor_user, client_record_id: int, entity_type: EntityType) -> None:
    ClientOnboardingOrchestrator(db).run(
        client_record_id,
        actor_id=actor_user.id,
        entity_type=entity_type,
        reference_date=date(2026, 1, 1),
    )


def _advance_payments(db, client_record_id: int):
    return db.scalars(
        select(AdvancePayment)
        .filter(AdvancePayment.client_record_id == client_record_id)
        .order_by(AdvancePayment.period.asc())
    ).all()


def test_company_ltd_monthly_advance_frequency_creates_monthly_payments(test_db, actor_user):
    client = _seed_client(
        test_db,
        name="חומוס אחלה",
        id_number="515555555",
        entity_type=EntityType.COMPANY_LTD,
        vat_frequency=VatType.MONTHLY,
        advance_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    _run_onboarding(test_db, actor_user, client.id, EntityType.COMPANY_LTD)

    payments = _advance_payments(test_db, client.id)

    assert [p.period for p in payments] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert all(p.period_months_count == 1 for p in payments)


def test_osek_murshe_bimonthly_advance_frequency_creates_bimonthly_payments(test_db, actor_user):
    client = _seed_client(
        test_db,
        name="עוסק מקדמות דו חודשי",
        id_number="212345678",
        entity_type=EntityType.OSEK_MURSHE,
        vat_frequency=VatType.MONTHLY,
        advance_frequency=AdvancePaymentFrequency.BIMONTHLY,
    )
    _run_onboarding(test_db, actor_user, client.id, EntityType.OSEK_MURSHE)

    payments = _advance_payments(test_db, client.id)

    assert [p.period for p in payments] == [
        "2026-01",
        "2026-03",
        "2026-05",
        "2026-07",
        "2026-09",
        "2026-11",
    ]
    assert all(p.period_months_count == 2 for p in payments)


def test_vat_reporting_frequency_does_not_drive_advance_payment_frequency(test_db, actor_user):
    client = _seed_client(
        test_db,
        name="מעום דו חודשי מקדמות חודשיות",
        id_number="212345679",
        entity_type=EntityType.OSEK_MURSHE,
        vat_frequency=VatType.BIMONTHLY,
        advance_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    _run_onboarding(test_db, actor_user, client.id, EntityType.OSEK_MURSHE)

    payments = _advance_payments(test_db, client.id)

    assert len(payments) == 12
    assert [p.period for p in payments] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert all(p.period_months_count == 1 for p in payments)
