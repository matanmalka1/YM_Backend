from datetime import date, timedelta

from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_VAT_WORK_ITEM_DELETED,
    ACTION_VAT_WORK_ITEM_UPDATED,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.common.enums import VatType
from app.utils.time_utils import utcnow
from app.vat.services.vat_report_service import VatReportService
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def test_update_work_item_metadata_touches_updated_at_and_audits_changed_fields(
    test_db, user_factory, create_client_with_business
):
    user = user_factory()
    client_record_id = create_client_with_business(
        full_name="VAT Metadata Client", id_number="VMD001", opened_at=date(2026, 1, 1)
    )[0].id
    service = VatReportService(test_db)
    item = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        pending_materials_note="old note",
    )
    old_updated_at = utcnow() - timedelta(days=1)
    item.updated_at = old_updated_at
    test_db.commit()

    updated = service.update_work_item_metadata(
        item_id=item.id,
        performed_by=user.id,
        patch={"pending_materials_note": "new note"},
    )

    assert updated.pending_materials_note == "new note"
    assert updated.updated_at > old_updated_at
    audit = test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_VAT_WORK_ITEM,
            EntityAuditLog.entity_id == item.id,
            EntityAuditLog.action == ACTION_VAT_WORK_ITEM_UPDATED,
        )
    ).one()
    assert audit.performed_by == user.id
    assert audit.old_value == {"pending_materials_note": "old note"}
    assert audit.new_value == {"pending_materials_note": "new note"}
    assert audit.metadata_json["client_record_id"] == client_record_id


def test_soft_delete_work_item_sets_delete_fields_updated_at_and_audit(
    test_db, user_factory, create_client_with_business
):
    user = user_factory()
    client_record_id = create_client_with_business(
        full_name="VAT Metadata Client", id_number="VMD001", opened_at=date(2026, 1, 1)
    )[0].id
    service = VatReportService(test_db)
    item = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    old_updated_at = utcnow() - timedelta(days=1)
    item.updated_at = old_updated_at
    test_db.commit()

    service.soft_delete_work_item(item_id=item.id, deleted_by=user.id)

    test_db.refresh(item)
    assert item.deleted_at is not None
    assert item.deleted_by == user.id
    assert item.updated_at > old_updated_at
    audit = test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_VAT_WORK_ITEM,
            EntityAuditLog.entity_id == item.id,
            EntityAuditLog.action == ACTION_VAT_WORK_ITEM_DELETED,
        )
    ).one()
    assert audit.performed_by == user.id
    assert audit.metadata_json["client_record_id"] == client_record_id
