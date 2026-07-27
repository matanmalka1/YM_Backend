from datetime import date

import pytest

from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.audit_constants import ACTION_BINDER_INTAKE_UPDATED, ENTITY_BINDER_INTAKE
from app.audit.repositories.audit_entity_audit_log_repository import (
    EntityAuditLogRepository,
)
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.models.binder_intake import BinderIntake
from app.binders.models.binder_intake_material import MaterialType
from app.binders.services.binder_intake_edit_service import BinderIntakeEditService
from app.businesses.models.business import Business, BusinessStatus
from app.common.enums import VatType
from app.core.exceptions import AppError
from app.vat.models.vat_work_item import VatWorkItem


def _business(business_factory, legal_entity_id: int, name: str) -> Business:
    return business_factory(
        legal_entity_id=legal_entity_id,
        business_name=name,
        status=BusinessStatus.ACTIVE,
        opened_at=date(2026, 1, 1),
        commit=True,
    )


def _annual_report(annual_report_row_factory, client_id: int, year: int) -> AnnualReport:
    return annual_report_row_factory(
        client_record_id=client_id,
        tax_year=year,
        commit=True,
    )


def _vat_work_item(
    vat_work_item_factory, client_id: int, period: str, created_by: int
) -> VatWorkItem:
    return vat_work_item_factory(
        client_record_id=client_id,
        created_by=created_by,
        period=period,
        period_type=VatType.MONTHLY,
        commit=True,
    )


def _binder(
    binder_factory,
    client_id: int,
    number: str,
    created_by: int,
    location_status: BinderLocationStatus = BinderLocationStatus.IN_OFFICE,
) -> Binder:
    return binder_factory(
        client_record_id=client_id,
        binder_number=number,
        period_start=date(2026, 1, 1),
        created_by=created_by,
        location_status=location_status,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )


def _intake_with_material(
    binder_intake_factory,
    binder_intake_material_factory,
    *,
    binder_id: int,
    received_by: int,
    business_id: int,
    annual_report_id: int,
    vat_report_id: int,
) -> BinderIntake:
    intake = binder_intake_factory(
        binder_id=binder_id,
        received_at=date(2026, 2, 8),
        received_by=received_by,
        notes="original notes",
    )
    binder_intake_material_factory(
        intake=intake,
        material_type=MaterialType.OTHER,
        business_id=business_id,
        annual_report_id=annual_report_id,
        vat_report_id=vat_report_id,
        period_year=2026,
        period_month_start=2,
        period_month_end=2,
        commit=True,
    )
    return intake


def test_edit_intake_moves_to_target_client_active_binder_and_logs_fk_changes(
    test_db,
    test_user,
    business_factory,
    binder_factory,
    client_factory,
    vat_work_item_factory,
    annual_report_row_factory,
    binder_intake_factory,
    binder_intake_material_factory,
):
    source_client = client_factory(
        full_name="Edit Intake 001", id_number="EDIT-001", office_client_number=100401
    )
    target_client = client_factory(
        full_name="Edit Intake 002", id_number="EDIT-002", office_client_number=100402
    )

    source_business = _business(business_factory, source_client.legal_entity_id, "Source Biz")
    target_business = _business(business_factory, target_client.legal_entity_id, "Target Biz")
    source_report = _annual_report(annual_report_row_factory, source_client.id, 2025)
    target_report = _annual_report(annual_report_row_factory, target_client.id, 2025)
    source_vat = _vat_work_item(vat_work_item_factory, source_client.id, "2026-02", test_user.id)
    target_vat = _vat_work_item(vat_work_item_factory, target_client.id, "2026-02", test_user.id)

    source_binder = _binder(binder_factory, source_client.id, "100401/1", test_user.id)
    target_binder = _binder(binder_factory, target_client.id, "100402/1", test_user.id)
    intake = _intake_with_material(
        binder_intake_factory,
        binder_intake_material_factory,
        binder_id=source_binder.id,
        received_by=test_user.id,
        business_id=source_business.id,
        annual_report_id=source_report.id,
        vat_report_id=source_vat.id,
    )

    service = BinderIntakeEditService(test_db)
    updated = service.edit_intake(
        intake_id=intake.id,
        actor_id=test_user.id,
        patch={
            "client_record_id": target_client.id,
            "business_ids": [target_business.id],
            "annual_report_ids": [target_report.id],
            "vat_report_ids": [target_vat.id],
        },
    )

    materials = service.material_repo.list_by_intake(updated.id)
    assert updated.binder_id == target_binder.id
    assert materials[0].business_id == target_business.id
    assert materials[0].annual_report_id == target_report.id
    assert materials[0].vat_report_id == target_vat.id

    rows = EntityAuditLogRepository(test_db).list_by_entity(ENTITY_BINDER_INTAKE, updated.id)
    assert rows, "intake edit must append binder_intake audit rows"
    assert all(row.action == ACTION_BINDER_INTAKE_UPDATED for row in rows)
    assert {row.metadata_json["field_name"] for row in rows} == {
        "client_record_id",
        "binder_id",
        f"material:{materials[0].id}.business_id",
        f"material:{materials[0].id}.annual_report_id",
        f"material:{materials[0].id}.vat_report_id",
    }
    # client context is threaded into metadata for every row.
    assert all(row.metadata_json["client_record_id"] for row in rows)


def test_edit_intake_rejects_cross_client_transfer_with_foreign_linked_entities(
    test_db,
    test_user,
    business_factory,
    binder_factory,
    client_factory,
    vat_work_item_factory,
    annual_report_row_factory,
    binder_intake_factory,
    binder_intake_material_factory,
):
    source_client = client_factory(
        full_name="Edit Intake 003", id_number="EDIT-003", office_client_number=100403
    )
    target_client = client_factory(
        full_name="Edit Intake 004", id_number="EDIT-004", office_client_number=100404
    )

    source_business = _business(business_factory, source_client.legal_entity_id, "Source Biz 2")
    source_report = _annual_report(annual_report_row_factory, source_client.id, 2024)
    source_vat = _vat_work_item(vat_work_item_factory, source_client.id, "2026-03", test_user.id)

    source_binder = _binder(binder_factory, source_client.id, "100403/1", test_user.id)
    _binder(binder_factory, target_client.id, "100404/1", test_user.id)
    intake = _intake_with_material(
        binder_intake_factory,
        binder_intake_material_factory,
        binder_id=source_binder.id,
        received_by=test_user.id,
        business_id=source_business.id,
        annual_report_id=source_report.id,
        vat_report_id=source_vat.id,
    )

    service = BinderIntakeEditService(test_db)
    with pytest.raises(AppError) as exc_info:
        service.edit_intake(
            intake_id=intake.id,
            actor_id=test_user.id,
            patch={
                "client_record_id": target_client.id,
                "business_ids": [source_business.id],
            },
        )

    assert exc_info.value.code == "BINDER.CROSS_CLIENT"
    assert service.intake_repo.get_by_id(intake.id).binder_id == source_binder.id
