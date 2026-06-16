from datetime import UTC, date, datetime, timedelta

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from app.vat.services.vat_report_service import VatReportService
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _user(test_db) -> User:
    user = User(
        full_name="VAT Query User",
        email="vat.query.user@example.com",
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
        official_name="VAT Query Client",
        id_number="VQS001",
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


def test_list_all_work_items_and_get_audit_trail(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
    service = VatReportService(test_db)
    now = datetime.now(UTC)

    older = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    newer = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    items, total = service.list_all_work_items(page=1, page_size=1)
    assert total == 2
    assert [item.id for item in items] == [newer.id]

    late = service.work_item_repo.append_audit(
        work_item_id=older.id, performed_by=user.id, action="late"
    )
    early = service.work_item_repo.append_audit(
        work_item_id=older.id, performed_by=user.id, action="early"
    )
    late.performed_at = now + timedelta(minutes=1)
    early.performed_at = now - timedelta(minutes=1)
    test_db.commit()

    trail = service.get_audit_trail(older.id, page=1, page_size=25)
    assert {entry.action for entry in trail} == {"early", "late"}


def test_list_work_items_filters_by_period_type(test_db):
    user = _user(test_db)
    _, monthly_client_id = _business(test_db)
    legal_entity = LegalEntity(
        official_name="VAT Query Client 2",
        id_number="VQS002",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    test_db.add(legal_entity)
    test_db.commit()
    client_record = ClientRecord(legal_entity_id=legal_entity.id)
    test_db.add(client_record)
    test_db.commit()

    service = VatReportService(test_db)
    monthly = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=monthly_client_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record.id,
        period="2026-01",
        period_type=VatType.BIMONTHLY,
        created_by=user.id,
    )

    items, total = service.list_all_work_items(period="2026-02", period_type=VatType.MONTHLY)

    assert total == 1
    assert items[0].id == monthly.id
