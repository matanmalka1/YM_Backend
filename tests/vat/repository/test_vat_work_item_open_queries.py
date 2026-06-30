from app.common.enums import VatType
from app.users.models.user import UserRole
from app.utils.time_utils import utcnow
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.factories import create_user
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _user(test_db):
    user = create_user(
        test_db,
        full_name="VAT Open Query User",
        email="vat.open.query@example.com",
        password="pass",
        role=UserRole.ADVISOR,
        is_active=True,
    )
    return user


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


def test_list_open_up_to_period_excludes_later_final_and_deleted_items(test_db):
    repo = VatWorkItemRepository(test_db)
    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="VAT Open Client", id_number="VOC001")
    deleted_client = seed_client_identity(
        test_db, full_name="VAT Deleted Client", id_number="VOC002"
    )
    oldest = _item(repo, client.id, user.id, "2026-01", VatWorkItemStatus.MATERIAL_RECEIVED)
    current = _item(repo, client.id, user.id, "2026-03", VatWorkItemStatus.PENDING_MATERIALS)
    _item(repo, client.id, user.id, "2026-04", VatWorkItemStatus.PENDING_MATERIALS)
    _item(repo, client.id, user.id, "2026-02", VatWorkItemStatus.FILED)
    deleted = _item(
        repo, deleted_client.id, user.id, "2026-02", VatWorkItemStatus.PENDING_MATERIALS
    )
    deleted.deleted_at = utcnow()
    test_db.commit()

    result = repo.list_open_up_to_period("2026-03", limit=10)

    assert [item.id for item in result] == [oldest.id, current.id]
