from datetime import date

from app.actions.services.obligation_orchestrator import _years_to_generate
from app.clients.client_create_policy import normalize_vat_exempt_ceiling
from app.clients.schemas.client_impact import ClientCreationImpactResponse, CreationImpactItem
from app.common.enums import (
    AdvancePaymentFrequency,
    EntityType,
    VatType,
)
from app.common.obligation_plan import (
    advance_payment_obligation_plan,
    vat_obligation_plan,
)
from app.utils.time_utils import israel_today


def compute_creation_impact(
    entity_type: EntityType | None,
    vat_reporting_frequency: VatType | None,
    advance_payment_frequency: AdvancePaymentFrequency | None = None,
    reference_date: date | None = None,
    *,
    vat_liable_from: date | None = None,
    vat_liable_to: date | None = None,
    advance_liable_from: date | None = None,
    advance_liable_to: date | None = None,
) -> ClientCreationImpactResponse:
    if entity_type == EntityType.EMPLOYEE:
        raise ValueError("פתיחת לקוח מסוג שכיר אינה נתמכת במערכת")

    today = reference_date or israel_today()
    years = _years_to_generate(today)
    n = len(years)
    is_exempt = vat_reporting_frequency in (VatType.EXEMPT, None)

    # The preview counts exactly what onboarding creates: every period the plan
    # lists. It used to filter on `entry.due_date >= today`, mirroring a guard in
    # the onboarding service that has since been removed — a late client owes its
    # past-due periods, and the liability range is what decides the boundary now.
    # Keeping the filter here would make the preview under-count what actually
    # gets created. Materializing calendar entries also left this read path, which
    # is a write a preview should never have been doing.
    vat_count = sum(
        len(
            vat_obligation_plan(
                vat_reporting_frequency,
                year,
                liable_from=vat_liable_from,
                liable_to=vat_liable_to,
            )
        )
        for year in years
    )
    advance_count = (
        sum(
            len(
                advance_payment_obligation_plan(
                    frequency=advance_payment_frequency,
                    year=year,
                    entity_type=entity_type,
                    liable_from=advance_liable_from,
                    liable_to=advance_liable_to,
                )
            )
            for year in years
        )
        if advance_payment_frequency is not None
        else 0
    )
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
