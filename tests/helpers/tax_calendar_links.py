from datetime import date, datetime
from itertools import count

from sqlalchemy import select

from app.advance_payments.models.advance_payment import AdvancePayment
from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.annual_reports.models.annual_report_enums import (
    ClientAnnualFilingType,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.clients.client_enums import ClientStatus
from app.common.enums import (
    AdvancePaymentFrequency,
    DeadlineRuleType,
    EntityType,
    ObligationStatus,
    ObligationType,
    VatType,
)
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.identity import seed_business, seed_client_identity

PATH = "/api/v1/tax-calendar/groups"

_identity_sequence = count(1)


def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


def get_or_create_deadline_rule(db, rule_type: DeadlineRuleType) -> DeadlineRule:
    existing = db.scalars(
        select(DeadlineRule).where(
            DeadlineRule.rule_type == rule_type.value,
            DeadlineRule.effective_to.is_(None),
        )
    ).first()
    if existing is not None:
        return existing
    rule = DeadlineRule(
        rule_type=rule_type,
        due_day_of_month=15,
        offset_months=1,
        effective_from=date(2024, 1, 1),
        effective_to=None,
    )
    db.add(rule)
    db.flush()
    return rule


def make_entry(
    db,
    *,
    obligation_type: ObligationType,
    rule_type: DeadlineRuleType,
    period: str | None,
    months: int | None,
    tax_year: int,
) -> TaxCalendarEntry:
    rule = get_or_create_deadline_rule(db, rule_type)
    entry = TaxCalendarEntry(
        obligation_type=obligation_type,
        period=period,
        period_months_count=months,
        tax_year=tax_year,
        due_date=date(tax_year + (0 if period else 1), 2, 15),
        deadline_rule_id=rule.id,
    )
    db.add(entry)
    db.flush()
    return entry


def advance_client(db, frequency=AdvancePaymentFrequency.MONTHLY):
    sequence = next(_identity_sequence)
    client = seed_client_identity(
        db,
        full_name=f"Calendar Advance {sequence}",
        id_number=f"CALADV{sequence:04d}",
        advance_payment_frequency=frequency,
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=f"Calendar Advance Biz {sequence}",
    )
    business.client_record_id = client.id
    db.flush()
    return client


def vat_client(db, vat_type: VatType):
    sequence = next(_identity_sequence)
    client = seed_client_identity(
        db,
        full_name=f"Calendar VAT {sequence}",
        id_number=f"CALVAT{sequence:04d}",
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=vat_type,
        status=ClientStatus.ACTIVE,
    )
    seed_business(db, legal_entity_id=client.legal_entity_id, business_name=f"VAT Biz {sequence}")
    db.flush()
    return client


def annual_client(db):
    sequence = next(_identity_sequence)
    return seed_client_identity(
        db,
        full_name=f"Calendar Annual {sequence}",
        id_number=f"CALANN{sequence:04d}",
    )


def vat_entry(db, year: int = 2026):
    return make_entry(
        db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        period=f"{year}-01",
        months=1,
        tax_year=year,
    )


def advance_entry(db, year: int = 2026):
    return make_entry(
        db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period=f"{year}-01",
        months=1,
        tax_year=year,
    )


def annual_entry(db, year: int = 2026):
    return make_entry(
        db,
        obligation_type=ObligationType.ANNUAL_REPORT,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        period=None,
        months=None,
        tax_year=year,
    )


def add_vat_item(db, entry, user_id: int, *, due_date=date(2026, 2, 20)):
    client_record = vat_client(db, VatType.MONTHLY)
    item = VatWorkItem(
        client_record_id=client_record.id,
        created_by=user_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        status=ObligationStatus.INPUT_RECEIVED,
        tax_calendar_entry_id=entry.id,
        due_date_original=entry.due_date,
        due_date_effective=due_date,
        due_date_override_reason="דחיית מועד",
    )
    db.add(item)
    db.flush()
    return item


def add_advance_payment(
    db,
    entry,
    *,
    due_date=date(2026, 2, 21),
    status=ObligationStatus.AWAITING_INPUT,
):
    client_record = advance_client(db)
    payment = AdvancePayment(
        client_record_id=client_record.id,
        period="2026-01",
        period_months_count=1,
        due_date=entry.due_date,
        due_date_original=entry.due_date,
        due_date_effective=due_date,
        due_date_override_reason="דחיית מועד",
        status=status,
        tax_calendar_entry_id=entry.id,
    )
    db.add(payment)
    db.flush()
    return payment


def add_annual_report(db, entry):
    client_record = annual_client(db)
    report = AnnualReport(
        client_record_id=client_record.id,
        tax_year=2026,
        client_type=ClientAnnualFilingType.SELF_EMPLOYED,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        status=ObligationStatus.AWAITING_INPUT,
        deadline_type=FilingDeadlineType.STANDARD,
        filing_deadline=datetime(2027, 7, 31, 10, 0),
        tax_calendar_entry_id=entry.id,
    )
    db.add(report)
    db.flush()
    return report


def create_tax_calendar_entry_for_period(db, obligation_type, period, period_months_count):
    return TaxCalendarMaterializationService(db).ensure_periodic_entry(
        obligation_type,
        period,
        period_months_count,
    )


def create_tax_calendar_entry_for_annual(db, tax_year):
    return TaxCalendarMaterializationService(db).ensure_annual_entry(tax_year)


def create_linked_vat_work_item(db, *, repo=None, period_type=VatType.MONTHLY, **kwargs):
    period_type_value = period_type.value if hasattr(period_type, "value") else period_type
    months = 2 if period_type_value == VatType.BIMONTHLY.value else 1
    entry = create_tax_calendar_entry_for_period(db, ObligationType.VAT, kwargs["period"], months)
    repo = repo or VatWorkItemRepository(db)
    kwargs.setdefault("status", ObligationStatus.INPUT_RECEIVED)
    kwargs.update(
        period_type=period_type,
        tax_calendar_entry_id=entry.id,
        due_date_original=entry.due_date,
        due_date_effective=entry.due_date,
    )
    return repo.create(**kwargs)


def create_linked_advance_payment(db, *, repo=None, period_months_count=1, **kwargs):
    entry = create_tax_calendar_entry_for_period(
        db,
        ObligationType.ADVANCE_PAYMENT,
        kwargs["period"],
        period_months_count,
    )
    repo = repo or AdvancePaymentRepository(db)
    kwargs.update(
        period_months_count=period_months_count,
        tax_calendar_entry_id=entry.id,
    )
    return repo.create(**kwargs)
