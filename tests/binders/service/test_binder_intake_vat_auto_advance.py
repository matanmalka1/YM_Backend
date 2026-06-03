"""
Flow-4 gap: VAT auto-advance path in BinderIntakeService.

When a binder intake includes a material with material_type='vat' and a vat_report_id
pointing to a PENDING_MATERIALS VatWorkItem, the service advances it to MATERIAL_RECEIVED
and writes an audit entry.
"""

from datetime import date

from sqlalchemy import select

from app.binders.services.binder_intake_service import BinderIntakeService
from app.common.enums import IdNumberType, VatType
from app.vat_reports.models.vat_audit_log import VatAuditLog
from app.vat_reports.models.vat_enums import VatWorkItemStatus
from app.vat_reports.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _setup(db, id_number: str, office_number: int):
    client = seed_client_identity(
        db,
        full_name=f"VAT Advance {id_number}",
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
        office_client_number=office_number,
    )
    business = seed_business(
        db,
        legal_entity_id=client.legal_entity_id,
        business_name=f"Business {id_number}",
        opened_at=date.today(),
    )
    db.commit()
    return client, business


def _vat_item(db, client_id: int, period: str, status: VatWorkItemStatus) -> VatWorkItem:
    return create_linked_vat_work_item(
        db,
        client_record_id=client_id,
        period=period,
        period_type=VatType.MONTHLY,
        status=status,
        created_by=1,
    )


def test_vat_material_advances_pending_materials_to_material_received(test_db, test_user):
    """material_type='vat' + PENDING_MATERIALS vat_report_id → MATERIAL_RECEIVED."""
    client, _ = _setup(test_db, "VA-001", 100501)
    vat_item = _vat_item(test_db, client.id, "2026-01", VatWorkItemStatus.PENDING_MATERIALS)

    BinderIntakeService(test_db).receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=[
            {
                "material_type": "vat",
                "vat_report_id": vat_item.id,
                "period_year": 2026,
                "period_month_start": 1,
                "period_month_end": 1,
            }
        ],
    )

    test_db.refresh(vat_item)
    assert vat_item.status == VatWorkItemStatus.MATERIAL_RECEIVED


def test_vat_material_advance_writes_audit_entry(test_db, test_user):
    """Status advance appends a VatAuditLog row with old/new status values."""
    client, _ = _setup(test_db, "VA-002", 100502)
    vat_item = _vat_item(test_db, client.id, "2026-02", VatWorkItemStatus.PENDING_MATERIALS)

    BinderIntakeService(test_db).receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=[
            {
                "material_type": "vat",
                "vat_report_id": vat_item.id,
                "period_year": 2026,
                "period_month_start": 2,
                "period_month_end": 2,
            }
        ],
    )

    audit_rows = list(
        test_db.scalars(select(VatAuditLog).where(VatAuditLog.work_item_id == vat_item.id))
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].old_value == VatWorkItemStatus.PENDING_MATERIALS.value
    assert audit_rows[0].new_value == VatWorkItemStatus.MATERIAL_RECEIVED.value
    assert audit_rows[0].performed_by == test_user.id


def test_vat_material_does_not_advance_non_pending_status(test_db, test_user):
    """material_type='vat' with status != PENDING_MATERIALS → no change."""
    client, _ = _setup(test_db, "VA-003", 100503)
    vat_item = _vat_item(test_db, client.id, "2026-03", VatWorkItemStatus.MATERIAL_RECEIVED)

    BinderIntakeService(test_db).receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=[
            {
                "material_type": "vat",
                "vat_report_id": vat_item.id,
                "period_year": 2026,
                "period_month_start": 3,
                "period_month_end": 3,
            }
        ],
    )

    test_db.refresh(vat_item)
    assert vat_item.status == VatWorkItemStatus.MATERIAL_RECEIVED


def test_non_vat_material_does_not_touch_vat_work_item(test_db, test_user):
    """material_type='other' → linked VatWorkItem untouched."""
    client, _ = _setup(test_db, "VA-004", 100504)
    vat_item = _vat_item(test_db, client.id, "2026-04", VatWorkItemStatus.PENDING_MATERIALS)

    BinderIntakeService(test_db).receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=[
            {
                "material_type": "other",
                "period_year": 2026,
                "period_month_start": 4,
                "period_month_end": 4,
                "description": "non-VAT document",
            }
        ],
    )

    test_db.refresh(vat_item)
    assert vat_item.status == VatWorkItemStatus.PENDING_MATERIALS


def test_duplicate_vat_report_id_advanced_only_once(test_db, test_user):
    """Same vat_report_id appearing twice in materials list is de-duped; one audit entry."""
    client, _ = _setup(test_db, "VA-005", 100505)
    vat_item = _vat_item(test_db, client.id, "2026-05", VatWorkItemStatus.PENDING_MATERIALS)
    mat = {
        "material_type": "vat",
        "vat_report_id": vat_item.id,
        "period_year": 2026,
        "period_month_start": 5,
        "period_month_end": 5,
    }

    BinderIntakeService(test_db).receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=[mat, mat],
    )

    test_db.refresh(vat_item)
    assert vat_item.status == VatWorkItemStatus.MATERIAL_RECEIVED

    audit_rows = list(
        test_db.scalars(select(VatAuditLog).where(VatAuditLog.work_item_id == vat_item.id))
    )
    assert len(audit_rows) == 1, "de-duped vat_report_id should produce a single audit entry"
