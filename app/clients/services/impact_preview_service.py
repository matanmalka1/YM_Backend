from datetime import date

from sqlalchemy.orm import Session

from app.actions.services.obligation_orchestrator import _years_to_generate
from app.clients.create_policy import normalize_vat_exempt_ceiling
from app.clients.schemas.impact import ClientCreationImpactResponse, CreationImpactItem
from app.common.enums import (
    AdvancePaymentFrequency,
    EntityType,
    ObligationType,
    VatType,
)
from app.common.obligation_plan import (
    advance_payment_obligation_plan,
    vat_obligation_plan,
)
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.utils.time_utils import israel_today


def compute_creation_impact(
    db: Session,
    entity_type: EntityType | None,
    vat_reporting_frequency: VatType | None,
    advance_payment_frequency: AdvancePaymentFrequency | None = None,
    reference_date: date | None = None,
) -> ClientCreationImpactResponse:
    if entity_type == EntityType.EMPLOYEE:
        raise ValueError("פתיחת לקוח מסוג שכיר אינה נתמכת במערכת")

    today = reference_date or israel_today()
    years = _years_to_generate(today)
    n = len(years)
    is_exempt = vat_reporting_frequency in (VatType.EXEMPT, None)
    tax_calendar = TaxCalendarMaterializationService(db)

    vat_count = 0
    for year in years:
        for plan in vat_obligation_plan(vat_reporting_frequency, year):
            entry = tax_calendar.ensure_periodic_entry(
                ObligationType.VAT,
                plan.period,
                plan.period_months_count,
            )
            if entry.due_date >= today:
                vat_count += 1
    if advance_payment_frequency is not None:
        advance_count = 0
        for year in years:
            for plan in advance_payment_obligation_plan(
                frequency=advance_payment_frequency,
                year=year,
                entity_type=entity_type,
            ):
                entry = tax_calendar.ensure_periodic_entry(
                    ObligationType.ADVANCE_PAYMENT,
                    plan.period,
                    plan.period_months_count,
                )
                if entry.due_date >= today:
                    advance_count += 1
    else:
        advance_count = 0
    items = [
        CreationImpactItem(label="קלסר פעיל", count=1),
        CreationImpactItem(label='דוחות מע"מ', count=vat_count),
        CreationImpactItem(label="רשומות מקדמות", count=advance_count),
        CreationImpactItem(label="דוח שנתי", count=n),
    ]
    items = [i for i in items if i.count > 0]

    if is_exempt and advance_count:
        note = 'פטור ממע"מ — לא ייווצרו מועדי מע"מ תקופתיים. ייווצרו מועדי מקדמות.'
    elif is_exempt:
        note = 'פטור ממע"מ — לא ייווצרו מועדי מע"מ תקופתיים.'
    else:
        note = None

    return ClientCreationImpactResponse(
        items=items,
        years_scope=n,
        note=note,
        vat_exempt_ceiling=normalize_vat_exempt_ceiling(entity_type),
    )
