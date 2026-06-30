from datetime import date

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType, VatType
from app.legal_entities.models.legal_entity import LegalEntity
from app.users.models.user import User, UserRole
from app.vat.services.vat_report_service import VatReportService
from tests.factories import create_user
from tests.helpers.identity import seed_client_with_business
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _user(test_db) -> User:
    user = create_user(
        test_db,
        full_name="VAT Query User",
        email="vat.query.user@example.com",
        password="pass",
        role=UserRole.ADVISOR,
        is_active=True,
        commit=True,
    )
    return user


def _business(test_db) -> tuple[Business, int]:
    client, business = seed_client_with_business(
        test_db,
        full_name="VAT Query Client",
        id_number="VQS001",
        opened_at=date(2026, 1, 1),
    )
    test_db.commit()
    test_db.refresh(business)
    return business, client.id


def test_list_all_work_items_paginated(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
    service = VatReportService(test_db)

    create_linked_vat_work_item(
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
