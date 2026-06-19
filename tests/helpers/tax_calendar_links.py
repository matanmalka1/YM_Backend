from app.advance_payments.repositories.advance_payment_repository import (
    AdvancePaymentRepository,
)
from app.common.enums import ObligationType, VatType
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository


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
    kwargs.setdefault("status", VatWorkItemStatus.MATERIAL_RECEIVED)
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
