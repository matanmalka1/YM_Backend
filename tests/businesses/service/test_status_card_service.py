"""
Flow-7 gap: dedicated tests for StatusCardService.get_status_card().

Covers aggregation logic and field computations for each card section.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.businesses.services.status_card_service import StatusCardService
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.common.enums import EntityType, IdNumberType
from app.core.exceptions import NotFoundError
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    PermanentDocumentType,
    PermanentDocument,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import (
    create_linked_vat_work_item,
    create_tax_calendar_entry_for_annual,
)


def _client(db, id_number: str) -> int:
    return seed_client_identity(
        db,
        full_name="Status Card Client",
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=EntityType.OSEK_MURSHE,
        office_client_number=200000 + int(id_number[-3:]),
    ).id


def test_not_found_raises(test_db):
    with pytest.raises(NotFoundError) as exc:
        StatusCardService(test_db).get_status_card(99999)
    assert exc.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_empty_client_returns_zero_counts(test_db):
    client_id = _client(test_db, "SC-EMPTY-001")
    card = StatusCardService(test_db).get_status_card(client_id, year=2026)

    assert card.client_id == client_id
    assert card.year == 2026
    assert card.client_vat.periods_total == 0
    assert card.client_vat.periods_filed == 0
    assert card.client_vat.net_vat_total == Decimal(0)
    assert card.client_vat.latest_period is None
    assert card.annual_report.status is None
    assert card.charges.unpaid_count == 0
    assert card.charges.total_outstanding == Decimal(0)
    assert card.advance_payments.count == 0
    assert card.advance_payments.total_paid == Decimal(0)
    assert card.binders.active_count == 0
    assert card.binders.in_office_count == 0
    assert card.documents.total_count == 0
    assert card.documents.present_count == 0


# ── VAT card ──────────────────────────────────────────────────────────────────


def test_vat_card_counts_only_requested_year(test_db):
    client_id = _client(test_db, "SC-VAT-001")
    for period, net_vat, status in [
        ("2026-01", Decimal("100.00"), VatWorkItemStatus.FILED),
        ("2026-02", Decimal("200.00"), VatWorkItemStatus.PENDING_MATERIALS),
        ("2025-12", Decimal("999.00"), VatWorkItemStatus.FILED),  # different year — excluded
    ]:
        item = create_linked_vat_work_item(
            test_db,
            client_record_id=client_id,
            period=period,
            status=status,
            created_by=1,
        )
        item.net_vat = net_vat
    test_db.flush()

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)

    assert card.client_vat.periods_total == 2
    assert card.client_vat.periods_filed == 1
    assert card.client_vat.net_vat_total == Decimal("300.00")
    assert card.client_vat.latest_period == "2026-02"


def test_vat_card_latest_period_is_lexicographic_max(test_db):
    client_id = _client(test_db, "SC-VAT-002")
    for period in ["2026-03", "2026-01", "2026-12", "2026-06"]:
        create_linked_vat_work_item(
            test_db,
            client_record_id=client_id,
            period=period,
            status=VatWorkItemStatus.PENDING_MATERIALS,
            created_by=1,
        )
    test_db.flush()

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)
    assert card.client_vat.latest_period == "2026-12"


# ── Annual report card ────────────────────────────────────────────────────────


def _annual_report(db, client_id: int, year: int, **kwargs) -> AnnualReport:
    entry = create_tax_calendar_entry_for_annual(db, year)
    report = AnnualReport(
        client_record_id=client_id,
        tax_year=year,
        client_type=ClientAnnualFilingType.SELF_EMPLOYED,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        tax_calendar_entry_id=entry.id,
        created_by=1,
        **kwargs,
    )
    db.add(report)
    db.flush()
    return report


def test_annual_report_card_reflects_stored_report(test_db):
    client_id = _client(test_db, "SC-AR-001")
    _annual_report(
        test_db,
        client_id,
        2026,
        status=AnnualReportStatus.IN_PREPARATION,
        filing_deadline=datetime(2027, 4, 30),
        refund_due=Decimal("1500.00"),
        tax_due=None,
    )

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)

    assert card.annual_report.status == AnnualReportStatus.IN_PREPARATION.value
    assert card.annual_report.form_type == PrimaryAnnualReportForm.FORM_1301.value
    assert card.annual_report.filing_deadline == "2027-04-30"
    assert card.annual_report.refund_due == Decimal("1500.00")
    assert card.annual_report.tax_due is None


def test_annual_report_card_empty_when_no_report_for_year(test_db):
    client_id = _client(test_db, "SC-AR-002")
    _annual_report(test_db, client_id, 2025, status=AnnualReportStatus.SUBMITTED)

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)
    assert card.annual_report.status is None


# ── Charges card ──────────────────────────────────────────────────────────────


def test_charges_card_sums_issued_charges_only(test_db):
    client_id = _client(test_db, "SC-CH-001")
    for amount, status in [
        (Decimal("500.00"), ChargeStatus.ISSUED),
        (Decimal("300.00"), ChargeStatus.ISSUED),
        (Decimal("200.00"), ChargeStatus.PAID),  # excluded
        (Decimal("100.00"), ChargeStatus.DRAFT),  # excluded
    ]:
        test_db.add(
            Charge(
                client_record_id=client_id,
                charge_type=ChargeType.MONTHLY_RETAINER,
                status=status,
                amount=amount,
            )
        )
    test_db.flush()

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)

    assert card.charges.unpaid_count == 2
    assert card.charges.total_outstanding == Decimal("800.00")


# ── Binders card ──────────────────────────────────────────────────────────────


def test_binders_card_counts_active_and_in_office(test_db):
    client_id = _client(test_db, "SC-BN-001")
    for location, capacity in [
        (BinderLocationStatus.IN_OFFICE, BinderCapacityStatus.OPEN),
        (BinderLocationStatus.IN_OFFICE, BinderCapacityStatus.FULL),
        (BinderLocationStatus.HANDED_OVER, BinderCapacityStatus.FULL),  # excluded from active
    ]:
        test_db.add(
            Binder(
                client_record_id=client_id,
                binder_number=f"200000/{location.value[:2]}-{capacity.value[:2]}",
                period_start=date(2026, 1, 1),
                created_by=1,
                location_status=location,
                capacity_status=capacity,
            )
        )
    test_db.flush()

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)

    assert card.binders.active_count == 2
    assert card.binders.in_office_count == 2


# ── Documents card ────────────────────────────────────────────────────────────


def test_documents_card_counts_present_separately(test_db, test_user):
    client_id = _client(test_db, "SC-DOC-001")
    for i, is_present in enumerate([True, True, False]):
        test_db.add(
            PermanentDocument(
                client_record_id=client_id,
                scope=DocumentScope.CLIENT,
                document_type=PermanentDocumentType.ID_COPY,
                storage_key=f"key-{i}-doc",
                is_present=is_present,
                uploaded_by=test_user.id,
            )
        )
    test_db.flush()

    card = StatusCardService(test_db).get_status_card(client_id, year=2026)

    assert card.documents.total_count == 3
    assert card.documents.present_count == 2


# ── Year default ──────────────────────────────────────────────────────────────


def test_year_defaults_to_current_year_when_not_provided(test_db):
    from app.utils.time_utils import utcnow

    client_id = _client(test_db, "SC-YR-001")
    card = StatusCardService(test_db).get_status_card(client_id)

    assert card.year == utcnow().year
