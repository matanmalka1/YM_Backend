"""Filtered work-queue builders must keep active-client scoping after moving their
queries into domain repositories: rows owned by a soft-deleted client are excluded.

vat_work_item_items already routed through a repository pre-refactor; annual_report
uses the same scope_to_active_clients_stmt helper exercised here via charges/advances.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.annual_reports.models.annual_report_enums import (
    AnnualReportStatus,
    ClientAnnualFilingType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.charges.charge_constants import UNPAID_CHARGE_TASK_THRESHOLD_DAYS
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.clients.client_enums import ClientStatus
from app.common.enums import IdNumberType, VatType
from app.utils.time_utils import utcnow
from app.work_queue.schemas.work_queue import WorkQueueSourceType
from app.work_queue.services.work_queue_service import WorkQueueService
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import (
    create_linked_advance_payment,
    create_tax_calendar_entry_for_annual,
)


def _deleted_client(test_db, suffix: str):
    return seed_client_identity(
        test_db,
        full_name=f"Builder Deleted {suffix}",
        id_number=f"BD-{suffix}",
        id_number_type=IdNumberType.INDIVIDUAL,
        vat_reporting_frequency=VatType.MONTHLY,
        status=ClientStatus.CLOSED,
        deleted_at=utcnow(),
    )


def test_charge_builder_excludes_soft_deleted_client(test_db):
    client = _deleted_client(test_db, "charge")
    charge = Charge(
        client_record_id=client.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        amount=Decimal("300.00"),
        issued_at=utcnow() - timedelta(days=UNPAID_CHARGE_TASK_THRESHOLD_DAYS + 5),
    )
    test_db.add(charge)
    test_db.commit()

    items = WorkQueueService(test_db).list_items()

    assert not [
        i for i in items if i.source_type == WorkQueueSourceType.CHARGE and i.source_id == charge.id
    ]


def test_advance_payment_builder_excludes_soft_deleted_client(test_db):
    client = _deleted_client(test_db, "adv")
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=client.id,
        period="2026-01",
        due_date=date.today(),
    )
    test_db.commit()

    items = WorkQueueService(test_db).list_items()

    assert not [
        i
        for i in items
        if i.source_type == WorkQueueSourceType.ADVANCE_PAYMENT and i.source_id == payment.id
    ]


def test_annual_report_builder_excludes_soft_deleted_client(test_db):
    client = _deleted_client(test_db, "annual")
    entry = create_tax_calendar_entry_for_annual(test_db, 2026)
    report = AnnualReport(
        client_record_id=client.id,
        tax_year=2026,
        client_type=ClientAnnualFilingType.SELF_EMPLOYED,
        form_type=PrimaryAnnualReportForm.FORM_1301,
        status=AnnualReportStatus.NOT_STARTED,
        tax_calendar_entry_id=entry.id,
        filing_deadline=date.today(),
        created_by=1,
    )
    test_db.add(report)
    test_db.commit()

    items = WorkQueueService(test_db).list_items()

    assert not [
        i
        for i in items
        if i.source_type == WorkQueueSourceType.ANNUAL_REPORT and i.source_id == report.id
    ]
