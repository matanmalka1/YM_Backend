from datetime import date

from sqlalchemy import func, select

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.clients.services.client_onboarding_orchestrator import (
    ClientOnboardingOrchestrator,
)
from app.clients.services.create_client_service import create_client_identity_only
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.tax_calendar.services.bootstrap import bootstrap_tax_calendar
from app.vat_reports.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_client_identity


def _create_vat_client(test_db, id_number: str):
    return create_client_identity_only(
        test_db,
        full_name="VAT Onboarding Client",
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        advance_rate="5.0",
        actor_id=1,
        reference_date=date(2026, 4, 30),
    )


def test_onboarding_creates_vat_work_items_and_advance_payments(test_db):
    client_record = _create_vat_client(test_db, "123456780")
    vat_items = list(
        test_db.scalars(select(VatWorkItem).where(VatWorkItem.client_record_id == client_record.id))
    )
    payments = list(
        test_db.scalars(
            select(AdvancePayment).where(AdvancePayment.client_record_id == client_record.id)
        )
    )
    reports = list(
        test_db.scalars(
            select(AnnualReport).where(AnnualReport.client_record_id == client_record.id)
        )
    )

    assert len(vat_items) == 9
    assert len(payments) == 9
    assert reports
    assert all(item.tax_calendar_entry_id is not None for item in vat_items)
    assert all(payment.tax_calendar_entry_id is not None for payment in payments)
    assert all(report.tax_calendar_entry_id is not None for report in reports)
    assert all(p.due_date_original == p.due_date for p in payments)
    assert all(p.due_date_effective == p.due_date for p in payments)


def test_onboarding_advance_payments_link_tax_calendar_entries(test_db):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    client_record = _create_vat_client(test_db, "123456786")

    payments = list(
        test_db.scalars(
            select(AdvancePayment).where(AdvancePayment.client_record_id == client_record.id)
        )
    )

    assert payments
    assert all(payment.tax_calendar_entry_id is not None for payment in payments)
    assert all(payment.due_date_original == payment.due_date for payment in payments)
    assert all(payment.due_date_effective == payment.due_date for payment in payments)


def test_onboarding_retry_does_not_duplicate_vat_work_items(test_db):
    client_record = _create_vat_client(test_db, "123456781")
    ClientOnboardingOrchestrator(test_db).run(
        client_record.id,
        actor_id=1,
        entity_type=EntityType.OSEK_MURSHE,
        reference_date=date(2026, 4, 30),
    )

    count = test_db.scalar(
        select(func.count(VatWorkItem.id)).where(VatWorkItem.client_record_id == client_record.id)
    )
    assert count == 9
    payment_count = test_db.scalar(
        select(func.count(AdvancePayment.id)).where(
            AdvancePayment.client_record_id == client_record.id
        )
    )
    assert payment_count == 9


def test_onboarding_does_not_create_empty_setup_placeholders(test_db):
    _create_vat_client(test_db, "123456782")

    from app.authority_contacts.models.authority_contact import AuthorityContact
    from app.notes.models.entity_note import EntityNote
    from app.documents.permanent_documents.models.permanent_document import PermanentDocument

    assert test_db.scalar(select(func.count(AuthorityContact.id))) == 0
    assert test_db.scalar(select(func.count(PermanentDocument.id))) == 0
    assert test_db.scalar(select(func.count(EntityNote.id))) == 0


def test_onboarding_exempt_client_creates_no_vat_items(test_db):
    seeded = seed_client_identity(
        test_db,
        full_name="Exempt Client",
        id_number="123456799",
        entity_type=EntityType.OSEK_PATUR,
        vat_reporting_frequency=VatType.EXEMPT,
        office_client_number=100999,
    )

    ClientOnboardingOrchestrator(test_db).run(
        seeded.id,
        actor_id=1,
        entity_type=EntityType.OSEK_PATUR,
        reference_date=date(2026, 4, 30),
    )

    assert (
        test_db.scalar(
            select(func.count(VatWorkItem.id)).where(VatWorkItem.client_record_id == seeded.id)
        )
        == 0
    )


def test_vat_bimonthly_advance_monthly_creates_12_advance_payments(test_db):
    """VAT bimonthly, advance monthly → 12 independent advance payments (not 6)."""
    client_record = create_client_identity_only(
        test_db,
        full_name="VAT Bimonthly Advance Monthly Client",
        id_number="123456790",
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.BIMONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        actor_id=1,
        reference_date=date(2025, 12, 31),
    )

    payments = list(
        test_db.scalars(
            select(AdvancePayment).where(AdvancePayment.client_record_id == client_record.id)
        )
    )
    # reference_date=2025-12-31 → years [2025, 2026]; 2025 yields 1 (2025-12), 2026 yields 12
    assert len(payments) == 13, f"Expected 13 advance payments (monthly), got {len(payments)}"
    assert all(p.period_months_count == 1 for p in payments)
