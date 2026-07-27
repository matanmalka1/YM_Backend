from datetime import date

from app.annual_reports.models.annual_report_enums import SubmissionMethod
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import VatType
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def test_status_listing_and_totals(test_db, user_factory, create_client_with_business):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client_record_id = create_client_with_business(opened_at=date(2026, 1, 1))[0].id

    oldest = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
    )
    newest = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-03",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        status=VatWorkItemStatus.PENDING_MATERIALS,
    )
    middle = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        status=VatWorkItemStatus.PENDING_MATERIALS,
    )

    by_status = repo.list_by_status(VatWorkItemStatus.PENDING_MATERIALS, page=1, page_size=10)
    assert [item.id for item in by_status] == [newest.id, middle.id]
    assert repo.count_by_status(VatWorkItemStatus.PENDING_MATERIALS) == 2

    all_items = repo.list_all(page=1, page_size=10)
    assert [item.period for item in all_items] == ["2026-03", "2026-02", "2026-01"]
    assert repo.count_all() == 3

    updated = repo.update_vat_totals(
        oldest.id,
        total_output_vat=170.0,
        total_input_vat=20.0,
        total_output_net=1000.0,
        total_input_net=200.0,
    )
    assert float(updated.total_output_vat) == 170.0
    assert float(updated.total_input_vat) == 20.0
    assert float(updated.net_vat) == 150.0


def test_global_work_item_lists_hide_deleted_clients_and_restore_visibility(
    test_db, user_factory, create_client_with_business
):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client_record_id = create_client_with_business(opened_at=date(2026, 1, 1))[0].id
    item = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-04",
        period_type=VatType.MONTHLY,
        created_by=user.id,
        status=VatWorkItemStatus.PENDING_MATERIALS,
    )

    record_repo = ClientRecordRepository(test_db)
    record_repo.soft_delete(client_record_id, deleted_by=user.id)

    assert item not in repo.list_all(page=1, page_size=10)
    assert repo.count_all() == 0

    record_repo.restore(client_record_id, restored_by=user.id)

    assert item in repo.list_all(page=1, page_size=10)
    assert repo.count_all() == 1


def test_mark_filed_persists_amendment_and_reference_fields(
    test_db, user_factory, create_client_with_business
):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client_record_id = create_client_with_business(opened_at=date(2026, 1, 1))[0].id
    item = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-11",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    amended_item = create_linked_vat_work_item(
        test_db,
        repo=repo,
        client_record_id=client_record_id,
        period="2026-10",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    filed = repo.mark_filed(
        item_id=item.id,
        final_vat_amount=321.5,
        submission_method=SubmissionMethod.ONLINE,
        filed_by=user.id,
        is_overridden=True,
        override_justification="manual override",
        submission_reference="REF-321",
        is_amendment=True,
        amends_item_id=amended_item.id,
    )

    assert filed is not None
    assert filed.status == VatWorkItemStatus.FILED
    assert float(filed.final_vat_amount) == 321.5
    assert filed.submission_reference == "REF-321"
    assert filed.is_amendment is True
    assert filed.amends_item_id == amended_item.id

    assert (
        repo.mark_filed(
            item_id=999999,
            final_vat_amount=1.0,
            submission_method=SubmissionMethod.MANUAL,
            filed_by=user.id,
        )
        is None
    )
