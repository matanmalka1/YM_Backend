from datetime import date

from app.binders.models.binder import BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository


def test_active_queries_and_soft_delete(test_db, user_factory, client_factory):
    repo = BinderRepository(test_db)
    user = user_factory()
    client_a = client_factory(full_name="Alpha", id_number="B001")
    client_b = client_factory(full_name="Beta", id_number="B002")

    binder_active = repo.create(
        client_record_id=client_a.id,
        binder_number="BA-1",
        period_start=date(2024, 3, 1),
        created_by=user.id,
    )
    binder_handed_over = repo.create(
        client_record_id=client_a.id,
        binder_number="BA-2",
        period_start=date(2024, 3, 2),
        created_by=user.id,
    )
    binder_handed_over.location_status = BinderLocationStatus.HANDED_OVER
    test_db.flush()

    _binder_other = repo.create(
        client_record_id=client_b.id,
        binder_number="BB-1",
        period_start=date(2024, 3, 3),
        created_by=user.id,
    )

    assert repo.get_active_by_number("BA-1").id == binder_active.id
    assert repo.get_active_by_number("BA-2") is None

    active_for_client = repo.list_active(client_record_id=client_a.id)
    assert [b.id for b in active_for_client] == [binder_active.id]

    assert repo.count_active() == 2  # binder_active + binder_other
    assert repo.count_active(client_record_id=client_a.id) == 1
    counts = repo.count_by_lifecycle_filtered()
    assert counts["location_in_office"] == 2
    assert counts["capacity_open"] == 3

    deleted = repo.soft_delete(binder_active.id, deleted_by=user.id)
    assert deleted is True
    assert repo.get_active_by_number("BA-1") is None
    assert repo.count_active() == 1
    assert repo.list_active(client_record_id=client_a.id) == []


def test_list_active_respects_sort_and_filters(test_db, user_factory, client_factory):
    repo = BinderRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Gamma", id_number="B003")

    older = repo.create(
        client_record_id=client.id,
        binder_number="BG-1",
        period_start=date(2024, 1, 1),
        created_by=user.id,
    )
    _newer = repo.create(
        client_record_id=client.id,
        binder_number="BG-2",
        period_start=date(2024, 2, 1),
        created_by=user.id,
    )

    default_order = repo.list_active()
    assert [b.binder_number for b in default_order] == ["BG-2", "BG-1"]

    asc_by_days = repo.list_active(sort_by="days_in_office", order="desc")
    assert [b.binder_number for b in asc_by_days] == ["BG-1", "BG-2"]

    number_filtered = repo.list_active(binder_number="G-1")
    assert [b.id for b in number_filtered] == [older.id]


def test_list_open_binders_sorts_null_period_start_last(test_db, user_factory, client_factory):
    repo = BinderRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Null Sort", id_number="B004")

    with_period = repo.create(
        client_record_id=client.id,
        binder_number="NULL-1",
        period_start=date(2024, 4, 1),
        created_by=user.id,
    )
    without_period = repo.create(
        client_record_id=client.id,
        binder_number="NULL-2",
        period_start=None,
        created_by=user.id,
    )

    ordered = repo.list_open_binders(page=1, page_size=20)

    assert [binder.id for binder in ordered[:2]] == [with_period.id, without_period.id]
