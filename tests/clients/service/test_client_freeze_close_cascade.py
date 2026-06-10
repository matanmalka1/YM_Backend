"""Integration tests for the freeze/close cascade (Flow 3).

Verifies that freezing or closing a client cascades to:
  - ClientRecord.status updated
  - All non-FILED VatWorkItems → CANCELED
  - All non-terminal AnnualReports → CANCELED
  - All IN_OFFICE binders → capacity_status = FULL (F-040 fixed)
"""

from datetime import date

from sqlalchemy import select

from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.clients.enums import ClientStatus
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.services.client_update_service import ClientUpdateService
from app.common.enums import EntityType, IdNumberType, VatType
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import (
    create_linked_vat_work_item,
    create_tax_calendar_entry_for_annual,
)


def _setup_client_with_cascade_data(db) -> int:
    seeded = seed_client_identity(
        db,
        full_name="Cascade Test Client",
        id_number="CASCADE-001",
        entity_type=EntityType.OSEK_MURSHE,
        id_number_type=IdNumberType.INDIVIDUAL,
        office_client_number=199001,
    )
    client_id = seeded.id

    create_linked_vat_work_item(
        db,
        client_record_id=client_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.PENDING_MATERIALS,
        created_by=1,
    )
    create_linked_vat_work_item(
        db,
        client_record_id=client_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
        created_by=1,
    )

    annual_entry = create_tax_calendar_entry_for_annual(db, 2026)
    db.add(
        AnnualReport(
            client_record_id=client_id,
            tax_year=2026,
            client_type=ClientAnnualFilingType.SELF_EMPLOYED,
            form_type=PrimaryAnnualReportForm.FORM_1301,
            status=AnnualReportStatus.NOT_STARTED,
            tax_calendar_entry_id=annual_entry.id,
            created_by=1,
        )
    )
    db.add(
        Binder(
            client_record_id=client_id,
            binder_number="199001/1",
            period_start=date(2026, 1, 1),
            created_by=1,
            location_status=BinderLocationStatus.IN_OFFICE,
            capacity_status=BinderCapacityStatus.OPEN,
        )
    )
    db.flush()
    return client_id


def test_freeze_cascade_cancels_vat_items_annual_reports_and_closes_binders(test_db):
    """freeze → status FROZEN, VatWorkItems CANCELED, AnnualReports CANCELED, binder FULL."""
    client_id = _setup_client_with_cascade_data(test_db)

    ClientUpdateService(test_db).update_client(client_id, actor_id=1, status=ClientStatus.FROZEN)
    test_db.flush()

    record = ClientRecordRepository(test_db).get_by_id(client_id)
    assert record is not None
    assert record.status == ClientStatus.FROZEN

    vat_items = list(
        test_db.scalars(select(VatWorkItem).where(VatWorkItem.client_record_id == client_id))
    )
    assert len(vat_items) == 2
    assert all(item.status == VatWorkItemStatus.CANCELED for item in vat_items)

    annual_reports = list(
        test_db.scalars(select(AnnualReport).where(AnnualReport.client_record_id == client_id))
    )
    assert len(annual_reports) == 1
    assert all(r.status == AnnualReportStatus.CANCELED for r in annual_reports)

    binders = list(test_db.scalars(select(Binder).where(Binder.client_record_id == client_id)))
    assert len(binders) == 1
    assert binders[0].capacity_status == BinderCapacityStatus.FULL
    assert binders[0].location_status == BinderLocationStatus.IN_OFFICE


def test_close_cascade_mirrors_freeze_cascade(test_db):
    """close → same cascade as freeze; CLOSED status persists."""
    client_id = _setup_client_with_cascade_data(test_db)

    ClientUpdateService(test_db).update_client(client_id, actor_id=1, status=ClientStatus.CLOSED)
    test_db.flush()

    record = ClientRecordRepository(test_db).get_by_id(client_id)
    assert record is not None
    assert record.status == ClientStatus.CLOSED

    vat_items = list(
        test_db.scalars(select(VatWorkItem).where(VatWorkItem.client_record_id == client_id))
    )
    assert all(item.status == VatWorkItemStatus.CANCELED for item in vat_items)

    binders = list(test_db.scalars(select(Binder).where(Binder.client_record_id == client_id)))
    assert all(b.capacity_status == BinderCapacityStatus.FULL for b in binders)


def test_freeze_does_not_cancel_filed_vat_items(test_db):
    """FILED VatWorkItems are excluded from bulk cancel on freeze."""
    seeded = seed_client_identity(
        test_db,
        full_name="Filed VAT Client",
        id_number="CASCADE-002",
        entity_type=EntityType.OSEK_MURSHE,
        id_number_type=IdNumberType.INDIVIDUAL,
        office_client_number=199002,
    )
    filed_item = create_linked_vat_work_item(
        test_db,
        client_record_id=seeded.id,
        period="2026-03",
        status=VatWorkItemStatus.FILED,
        created_by=1,
    )

    ClientUpdateService(test_db).update_client(seeded.id, actor_id=1, status=ClientStatus.FROZEN)
    test_db.refresh(filed_item)

    assert filed_item.status == VatWorkItemStatus.FILED


def test_binder_already_full_stays_full_after_cascade(test_db):
    """IN_OFFICE FULL binder stays FULL (idempotent) when client is frozen."""
    seeded = seed_client_identity(
        test_db,
        full_name="Full Binder Client",
        id_number="CASCADE-003",
        entity_type=EntityType.OSEK_MURSHE,
        id_number_type=IdNumberType.INDIVIDUAL,
        office_client_number=199003,
    )
    binder = Binder(
        client_record_id=seeded.id,
        binder_number="199003/1",
        period_start=date(2026, 1, 1),
        created_by=1,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.FULL,
    )
    test_db.add(binder)
    test_db.flush()

    ClientUpdateService(test_db).update_client(seeded.id, actor_id=1, status=ClientStatus.FROZEN)
    test_db.refresh(binder)

    assert binder.capacity_status == BinderCapacityStatus.FULL
    assert binder.location_status == BinderLocationStatus.IN_OFFICE
