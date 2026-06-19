from datetime import date, timedelta

from sqlalchemy import select

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from app.utils.time_utils import utcnow
from app.vat.models.vat_audit_log import VatAuditLog
from app.vat.services.vat_report_service import VatReportService
from app.vat.vat_constants import (
    ACTION_METADATA_UPDATED,
    ACTION_WORK_ITEM_DELETED,
)
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _user(test_db) -> User:
    user = User(
        full_name="VAT Metadata User",
        email="vat.metadata.user@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db) -> tuple[Business, int]:
    legal_entity = LegalEntity(
        official_name="VAT Metadata Client",
        id_number="VMD001",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    test_db.add(legal_entity)
    test_db.commit()
    test_db.refresh(legal_entity)

    client_record = ClientRecord(legal_entity_id=legal_entity.id)
    test_db.add(client_record)
    test_db.commit()
    test_db.refresh(client_record)

    business = Business(
        legal_entity_id=legal_entity.id,
        business_name=legal_entity.official_name,
        opened_at=date(2026, 1, 1),
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business, client_record.id


def test_update_work_item_metadata_touches_updated_at_and_audits_changed_fields(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
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
        select(VatAuditLog).where(
            VatAuditLog.work_item_id == item.id,
            VatAuditLog.action == ACTION_METADATA_UPDATED,
        )
    ).one()
    assert audit.performed_by == user.id
    assert '"pending_materials_note": "old note"' in audit.old_value
    assert '"pending_materials_note": "new note"' in audit.new_value


def test_soft_delete_work_item_sets_delete_fields_updated_at_and_audit(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
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
        select(VatAuditLog).where(
            VatAuditLog.work_item_id == item.id,
            VatAuditLog.action == ACTION_WORK_ITEM_DELETED,
        )
    ).one()
    assert audit.performed_by == user.id
