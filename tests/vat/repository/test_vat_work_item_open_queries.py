from app.common.enums import ObligationStatus, VatType
from app.utils.time_utils import utcnow
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _item(repo, client_id: int, user_id: int, period: str, status):
    return create_linked_vat_work_item(
        repo.db,
        repo=repo,
        client_record_id=client_id,
        period=period,
        period_type=VatType.MONTHLY,
        created_by=user_id,
        status=status,
    )


def test_list_open_up_to_period_excludes_later_final_and_deleted_items(
    test_db, user_factory, client_factory
):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="VAT Open Client", id_number="VOC001")
    deleted_client = client_factory(full_name="VAT Deleted Client", id_number="VOC002")
    oldest = _item(repo, client.id, user.id, "2026-01", ObligationStatus.INPUT_RECEIVED)
    current = _item(repo, client.id, user.id, "2026-03", ObligationStatus.AWAITING_INPUT)
    _item(repo, client.id, user.id, "2026-04", ObligationStatus.AWAITING_INPUT)
    _item(repo, client.id, user.id, "2026-02", ObligationStatus.SUBMITTED)
    deleted = _item(repo, deleted_client.id, user.id, "2026-02", ObligationStatus.AWAITING_INPUT)
    deleted.deleted_at = utcnow()
    test_db.commit()

    result = repo.list_open_up_to_period("2026-03", limit=10)

    assert [item.id for item in result] == [oldest.id, current.id]
