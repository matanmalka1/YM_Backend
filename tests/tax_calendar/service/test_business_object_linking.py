from datetime import date

import pytest
from sqlalchemy import func, select

from app.advance_payments.services.advance_payment_generation_service import (
    generate_annual_schedule,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.common.enums import DeadlineRuleType, ObligationType, VatType
from app.core.exceptions import AppError, ConflictError
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.tax_calendar.services.tax_calendar_bootstrap_service import bootstrap_tax_calendar
from app.tax_calendar.services.tax_calendar_grouped_service import list_groups_paginated
from app.tax_calendar.services.tax_calendar_materialization_service import (
    TaxCalendarMaterializationService,
)
from app.tax_calendar.tax_calendar_link_diagnostics import (
    find_active_null_tax_calendar_links,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from app.vat.services.vat_intake_service import create_work_item
from tests.tax_calendar.service.linking_helpers import (
    advance_client,
    annual_client,
    make_entry,
    vat_client,
)


def test_advance_payment_generation_links_matching_tax_calendar_entry(test_db):
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.ADVANCE_PAYMENT,
        rule_type=DeadlineRuleType.ADVANCE_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    client = advance_client(test_db)

    created, skipped = generate_annual_schedule(
        client.id, 2026, test_db, reference_date=date(2025, 12, 31)
    )

    jan = next(payment for payment in created if payment.period == "2026-01")
    assert skipped == 0
    assert jan.tax_calendar_entry_id == entry.id
    assert jan.due_date == date(2026, 2, 15)
    assert jan.status.value == "pending"


def test_advance_payment_generation_creates_missing_tax_calendar_entry(test_db):
    client = advance_client(test_db)

    created, _ = generate_annual_schedule(
        client.id, 2026, test_db, reference_date=date(2025, 12, 31)
    )

    assert all(payment.tax_calendar_entry_id is not None for payment in created)
    jan = next(payment for payment in created if payment.period == "2026-01")
    entry = test_db.get(TaxCalendarEntry, jan.tax_calendar_entry_id)
    assert entry.obligation_type == ObligationType.ADVANCE_PAYMENT
    assert entry.period == "2026-01"
    assert entry.period_months_count == 1


def test_vat_work_item_monthly_links_matching_tax_calendar_entry(test_db, actor_user):
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    client = vat_client(test_db, VatType.MONTHLY)

    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )

    assert item.tax_calendar_entry_id == entry.id
    assert item.due_date_original == entry.due_date
    assert item.due_date_effective == entry.due_date
    assert item.status == VatWorkItemStatus.MATERIAL_RECEIVED


def test_vat_work_item_bimonthly_links_matching_tax_calendar_entry(test_db, actor_user):
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_BIMONTHLY,
        period="2026-01",
        months=2,
        tax_year=2026,
    )
    client = vat_client(test_db, VatType.BIMONTHLY)

    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )

    assert item.tax_calendar_entry_id == entry.id
    assert item.due_date_original == entry.due_date
    assert item.due_date_effective == entry.due_date
    assert item.status == VatWorkItemStatus.MATERIAL_RECEIVED


def test_materializer_rejects_even_month_bimonthly_calendar_entry(test_db):
    make_entry(
        test_db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_BIMONTHLY,
        period="2026-01",
        months=2,
        tax_year=2026,
    )

    with pytest.raises(AppError) as exc:
        TaxCalendarMaterializationService(test_db).ensure_periodic_entry(
            ObligationType.VAT,
            "2026-02",
            2,
        )

    assert exc.value.code == "TAX_CALENDAR.INVALID_PERIOD_ALIGNMENT"


def test_vat_work_item_creates_missing_tax_calendar_entry(test_db, actor_user):
    client = vat_client(test_db, VatType.MONTHLY)

    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )

    entry = test_db.get(TaxCalendarEntry, item.tax_calendar_entry_id)
    assert entry.obligation_type == ObligationType.VAT
    assert entry.period == "2026-01"
    assert entry.period_months_count == 1
    assert item.due_date_original == entry.due_date
    assert item.due_date_effective == entry.due_date
    assert item.status == VatWorkItemStatus.MATERIAL_RECEIVED


def test_vat_work_item_due_date_original_is_immutable_after_set(test_db, actor_user):
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    client = vat_client(test_db, VatType.MONTHLY)
    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )

    item.due_date_original = date(2026, 2, 20)

    with pytest.raises(ValueError):
        test_db.flush()
    assert item.due_date_effective == entry.due_date


def test_vat_work_item_effective_due_date_requires_reason_when_changed(test_db, actor_user):
    client = vat_client(test_db, VatType.MONTHLY)
    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )
    item.due_date_original = date(2026, 2, 15)
    item.due_date_effective = date(2026, 2, 20)

    with pytest.raises(ValueError):
        test_db.flush()


def test_vat_work_item_effective_due_date_can_change_with_reason(test_db, actor_user):
    client = vat_client(test_db, VatType.MONTHLY)
    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )
    # due_date_original is already set from TaxCalendarEntry; only change effective.
    item.due_date_effective = date(2026, 2, 20)
    item.due_date_override_reason = "דחייה רשמית"

    test_db.flush()

    assert item.due_date_effective == date(2026, 2, 20)


def test_vat_work_item_effective_due_date_equal_original_needs_no_reason(test_db, actor_user):
    client = vat_client(test_db, VatType.MONTHLY)
    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )
    # Setting effective to the same value as original requires no override reason.
    item.due_date_effective = item.due_date_original

    test_db.flush()

    assert item.due_date_override_reason is None


def test_vat_exempt_keeps_existing_rejection_before_calendar_linking(test_db, actor_user):
    client = vat_client(test_db, VatType.EXEMPT)

    with pytest.raises(AppError) as exc:
        create_work_item(
            VatWorkItemRepository(test_db),
            test_db,
            client_record_id=client.id,
            period="2026-01",
            created_by=actor_user.id,
        )

    assert exc.value.code == "VAT.CLIENT_EXEMPT"
    assert test_db.scalar(select(func.count()).select_from(VatWorkItem)) == 0


def test_annual_report_creation_links_matching_tax_calendar_entry(test_db, actor_user):
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.ANNUAL_REPORT,
        rule_type=DeadlineRuleType.ANNUAL_REPORT,
        period=None,
        months=None,
        tax_year=2026,
    )
    client = annual_client(test_db)

    report = AnnualReportService(test_db).create_report(
        client.id, 2026, "corporation", actor_user.id, actor_user.full_name
    )

    assert report.tax_calendar_entry_id == entry.id
    assert report.status.value == "not_started"
    assert report.filing_deadline.date() == date(2027, 7, 31)


def test_annual_report_creation_creates_missing_tax_calendar_entry(test_db, actor_user):
    client = annual_client(test_db)

    report = AnnualReportService(test_db).create_report(
        client.id, 2026, "corporation", actor_user.id, actor_user.full_name
    )

    entry = test_db.get(TaxCalendarEntry, report.tax_calendar_entry_id)
    assert entry.obligation_type == ObligationType.ANNUAL_REPORT
    assert entry.tax_year == 2026


def test_mismatched_existing_tax_calendar_fk_raises_conflict(test_db, actor_user):
    wrong = make_entry(
        test_db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        period="2026-02",
        months=1,
        tax_year=2026,
    )
    client = vat_client(test_db, VatType.MONTHLY)
    item = VatWorkItem(
        client_record_id=client.id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=actor_user.id,
        tax_calendar_entry_id=wrong.id,
        due_date_original=wrong.due_date,
        due_date_effective=wrong.due_date,
    )
    test_db.add(item)
    test_db.flush()

    with pytest.raises(ConflictError):
        TaxCalendarMaterializationService(test_db).link_vat_work_item(item)


def test_grouped_tax_calendar_sees_newly_materialized_rows(test_db, actor_user):
    client = vat_client(test_db, VatType.MONTHLY)
    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=actor_user.id,
    )

    result = list_groups_paginated(
        test_db,
        tax_year_after=2026,
        tax_year_before=2026,
        obligation_type=ObligationType.VAT,
        include_empty=False,
    )

    assert any(
        group.tax_calendar_entry_id == item.tax_calendar_entry_id and group.linked_count == 1
        for group in result.items
    )


def test_null_link_diagnostics_reports_active_rows(test_db):
    assert find_active_null_tax_calendar_links(test_db) == {
        "vat_work_items": {"count": 0, "ids": []},
        "advance_payments": {"count": 0, "ids": []},
        "annual_reports": {"count": 0, "ids": []},
    }


def test_bootstrap_entries_allow_business_objects_to_link(test_db, actor_user):
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2026)
    advance = advance_client(test_db)
    vat = vat_client(test_db, VatType.MONTHLY)
    annual = annual_client(test_db)

    payments, skipped = generate_annual_schedule(
        advance.id, 2026, test_db, reference_date=date(2025, 12, 31)
    )
    vat_item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=vat.id,
        period="2026-01",
        created_by=actor_user.id,
    )
    report = AnnualReportService(test_db).create_report(
        annual.id, 2026, "corporation", actor_user.id, actor_user.full_name
    )

    assert skipped == 0
    assert payments[0].tax_calendar_entry_id is not None
    assert vat_item.tax_calendar_entry_id is not None
    assert report.tax_calendar_entry_id is not None
