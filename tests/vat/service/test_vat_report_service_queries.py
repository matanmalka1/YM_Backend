from datetime import date

from app.common.enums import IdNumberType, VatType
from app.vat.services.vat_report_service import VatReportService
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def test_list_all_work_items_paginated(test_db, user_factory, create_client_with_business):
    user = user_factory()
    client_record_id = create_client_with_business(
        full_name="VAT Query Client", id_number="VQS001", opened_at=date(2026, 1, 1)
    )[0].id
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


def test_list_work_items_filters_by_period_type(
    test_db, user_factory, client_factory, create_client_with_business
):
    user = user_factory()
    monthly_client_id = create_client_with_business(
        full_name="VAT Query Client", id_number="VQS001", opened_at=date(2026, 1, 1)
    )[0].id
    other_client = client_factory(
        full_name="VAT Query Client 2",
        id_number="VQS002",
        id_number_type=IdNumberType.INDIVIDUAL,
        create_person=False,
        commit=True,
    )

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
        client_record_id=other_client.id,
        period="2026-01",
        period_type=VatType.BIMONTHLY,
        created_by=user.id,
    )

    items, total = service.list_all_work_items(period="2026-02", period_type=VatType.MONTHLY)

    assert total == 1
    assert items[0].id == monthly.id
