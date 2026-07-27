from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.services.client_create_service import create_client_identity_only
from app.common.enums import EntityType, IdNumberType


def _create_client(db, actor_user, *, full_name: str, id_number: str, deleted: bool = False):
    record = create_client_identity_only(
        db,
        full_name=full_name,
        id_number=id_number,
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.COMPANY_LTD,
        actor_id=actor_user.id,
    )
    if deleted:
        ClientRecordRepository(db).soft_delete(record.id, deleted_by=actor_user.id)
        record = ClientRecordRepository(db).get_by_id_including_deleted(record.id)
    return record


def test_create_and_get_by_id_filters_deleted(test_db, actor_user):
    repo = ClientRecordRepository(test_db)
    created = create_client_identity_only(
        test_db,
        full_name="Repo Client",
        id_number="100000001",
        id_number_type=IdNumberType.CORPORATION,
        entity_type=EntityType.COMPANY_LTD,
        actor_id=actor_user.id,
    )

    assert repo.get_by_id(created.id) is not None

    assert repo.soft_delete(created.id, deleted_by=actor_user.id) is True
    assert repo.get_by_id(created.id) is None
    assert repo.get_by_id_including_deleted(created.id) is not None


def test_get_active_and_deleted_by_id_number(test_db, actor_user):
    repo = ClientRecordRepository(test_db)
    active = _create_client(test_db, actor_user, full_name="Active", id_number="200000001")
    deleted = _create_client(
        test_db, actor_user, full_name="Deleted", id_number="200000002", deleted=True
    )

    active_rows = repo.get_active_by_id_number("200000001")
    deleted_rows = repo.get_deleted_by_id_number("200000002")
    all_rows_active = [
        *repo.get_active_by_id_number("200000001"),
        *repo.get_deleted_by_id_number("200000001"),
    ]
    all_rows_deleted = [
        *repo.get_active_by_id_number("200000002"),
        *repo.get_deleted_by_id_number("200000002"),
    ]

    assert [c.id for c in active_rows] == [active.id]
    assert [c.id for c in deleted_rows] == [deleted.id]
    assert [c.id for c in all_rows_active] == [active.id]
    assert [c.id for c in all_rows_deleted] == [deleted.id]
    assert repo.get_active_by_id_number("200000001")[0].id == active.id


def test_restore_clears_deleted_fields(test_db, actor_user):
    client = _create_client(
        test_db, actor_user, full_name="Restore Me", id_number="300000001", deleted=True
    )
    repo = ClientRecordRepository(test_db)

    restored = repo.restore(client.id, restored_by=actor_user.id)

    assert restored is not None
    assert restored.deleted_at is None
    assert restored.deleted_by is None
    assert restored.restored_at is not None
    assert restored.restored_by == 7
    assert repo.restore(restored.id, restored_by=actor_user.id) is None


def test_list_count_search_and_list_by_ids(test_db, actor_user):
    _create_client(test_db, actor_user, full_name="Alice One", id_number="400000001")
    bob = _create_client(test_db, actor_user, full_name="Bob Two", id_number="400000002")
    deleted = _create_client(
        test_db, actor_user, full_name="Deleted Three", id_number="499999999", deleted=True
    )

    repo = ClientRecordRepository(test_db)

    items_page_1 = repo.list(page=1, page_size=1)
    assert len(items_page_1) == 1

    search_items, search_total = repo.search(search="Bob", page=1, page_size=10)
    assert search_total == 1
    assert [c.id for c in search_items] == [bob.id]

    filtered = repo.count(search="40000000")
    assert filtered == 2

    by_ids = repo.list_by_ids([bob.id, deleted.id])
    assert [c.id for c in by_ids] == [bob.id]

    search_items, search_total = repo.search(
        search="Bob", id_number="400000002", page=1, page_size=10
    )
    assert search_total == 1
    assert [c.id for c in search_items] == [bob.id]

    assert repo.list_by_ids([]) == []


def test_soft_delete_returns_false_for_missing_client(test_db, actor_user):
    repo = ClientRecordRepository(test_db)
    assert repo.soft_delete(9999, deleted_by=actor_user.id) is False
