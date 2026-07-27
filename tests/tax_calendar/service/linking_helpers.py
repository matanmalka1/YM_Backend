from datetime import date
from itertools import count

from sqlalchemy import select

from app.clients.client_enums import ClientStatus
from app.common.enums import (
    AdvancePaymentFrequency,
    DeadlineRuleType,
    EntityType,
    ObligationType,
    VatType,
)
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from tests.helpers.identity import seed_business, seed_client_identity

seq = count(1)


def _get_or_create_rule(db, rule_type: DeadlineRuleType) -> DeadlineRule:
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
    rule = _get_or_create_rule(db, rule_type)
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
    idx = next(seq)
    client = seed_client_identity(
        db,
        full_name=f"Calendar Advance {idx}",
        id_number=f"CALADV{idx:04d}",
        advance_payment_frequency=frequency,
    )
    business = seed_business(
        db, legal_entity_id=client.legal_entity_id, business_name=f"Calendar Advance Biz {idx}"
    )
    business.client_record_id = client.id
    db.flush()
    return client


def vat_client(db, vat_type: VatType):
    idx = next(seq)
    client = seed_client_identity(
        db,
        full_name=f"Calendar VAT {idx}",
        id_number=f"CALVAT{idx:04d}",
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=vat_type,
        status=ClientStatus.ACTIVE,
    )
    seed_business(db, legal_entity_id=client.legal_entity_id, business_name=f"VAT Biz {idx}")
    db.flush()
    return client


def annual_client(db):
    idx = next(seq)
    return seed_client_identity(
        db, full_name=f"Calendar Annual {idx}", id_number=f"CALANN{idx:04d}"
    )
