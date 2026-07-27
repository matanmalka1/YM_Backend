"""Filter coverage for the open-binders operational list."""

from datetime import date

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.binders.services.binder_operations_service import BinderOperationsService
from app.utils.time_utils import start_of_day


def _binder(binder_factory, db, client_id, user_id, number, period_start, *, created_on=None):
    binder = binder_factory(
        client_record_id=client_id,
        binder_number=number,
        period_start=period_start,
        created_by=user_id,
    )
    if created_on is not None:
        binder.created_at = start_of_day(created_on)
        db.commit()
        db.refresh(binder)
    return binder


def test_open_binders_filter_by_client_record_id(
    test_db, test_user, client_factory, binder_factory
):
    client_a = client_factory(full_name="A", id_number="OF-001")
    client_b = client_factory(full_name="B", id_number="OF-002")
    target = _binder(binder_factory, test_db, client_a.id, test_user.id, "B-A", date(2024, 1, 1))
    _binder(binder_factory, test_db, client_b.id, test_user.id, "B-B", date(2024, 1, 2))

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(client_record_id=client_a.id)

    assert total == 1
    assert [b.id for b in items] == [target.id]


def test_open_binders_filter_by_binder_number(test_db, test_user, client_factory, binder_factory):
    client = client_factory(full_name="A", id_number="OF-003")
    target = _binder(
        binder_factory, test_db, client.id, test_user.id, "INV-2024-7", date(2024, 1, 1)
    )
    _binder(binder_factory, test_db, client.id, test_user.id, "OTHER-9", date(2024, 1, 2))

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(binder_number="2024-7")

    assert total == 1
    assert [b.id for b in items] == [target.id]


def test_open_binders_filter_by_created_date_range(
    test_db, test_user, client_factory, binder_factory
):
    client = client_factory(full_name="A", id_number="OF-004")
    _binder(
        binder_factory,
        test_db,
        client.id,
        test_user.id,
        "B-JAN",
        date(2024, 1, 1),
        created_on=date(2024, 1, 10),
    )
    mar = _binder(
        binder_factory,
        test_db,
        client.id,
        test_user.id,
        "B-MAR",
        date(2024, 3, 1),
        created_on=date(2024, 3, 10),
    )

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(
        created_after=date(2024, 2, 1), created_before=date(2024, 3, 31)
    )

    assert total == 1
    assert [b.id for b in items] == [mar.id]


def test_open_binders_created_before_is_inclusive_of_whole_day(
    test_db, test_user, client_factory, binder_factory
):
    client = client_factory(full_name="A", id_number="OF-005")
    # created_at set to midnight of 2024-03-10; created_before=2024-03-10 must include it.
    b = _binder(
        binder_factory,
        test_db,
        client.id,
        test_user.id,
        "B-EDGE",
        date(2024, 3, 1),
        created_on=date(2024, 3, 10),
    )

    service = BinderOperationsService(test_db)
    _items, total = service.get_open_binders(created_before=date(2024, 3, 10))

    assert total == 1
    assert _items[0].id == b.id


def test_open_binders_filters_combined_with_and(test_db, test_user, client_factory, binder_factory):
    client_a = client_factory(full_name="A", id_number="OF-006")
    client_b = client_factory(full_name="B", id_number="OF-007")
    match = _binder(
        binder_factory,
        test_db,
        client_a.id,
        test_user.id,
        "MATCH-1",
        date(2024, 2, 1),
        created_on=date(2024, 2, 5),
    )
    # Same client, wrong date.
    _binder(
        binder_factory,
        test_db,
        client_a.id,
        test_user.id,
        "MATCH-2",
        date(2024, 2, 1),
        created_on=date(2024, 9, 5),
    )
    # Right date, wrong client.
    _binder(
        binder_factory,
        test_db,
        client_b.id,
        test_user.id,
        "MATCH-3",
        date(2024, 2, 1),
        created_on=date(2024, 2, 5),
    )

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(
        client_record_id=client_a.id,
        created_after=date(2024, 2, 1),
        created_before=date(2024, 2, 28),
    )

    assert total == 1
    assert [b.id for b in items] == [match.id]


def test_open_binders_no_match_returns_empty(test_db, test_user, client_factory, binder_factory):
    client = client_factory(full_name="A", id_number="OF-008")
    _binder(binder_factory, test_db, client.id, test_user.id, "B-1", date(2024, 1, 1))

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(client_record_id=999999)

    assert total == 0
    assert items == []


def test_open_binders_capacity_status_filter(test_db, test_user, client_factory, binder_factory):
    client = client_factory(full_name="A", id_number="OF-009")
    full = _binder(binder_factory, test_db, client.id, test_user.id, "B-FULL", date(2024, 1, 1))
    full.capacity_status = BinderCapacityStatus.FULL
    test_db.commit()
    _binder(binder_factory, test_db, client.id, test_user.id, "B-OPEN", date(2024, 1, 2))

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(capacity_status=BinderCapacityStatus.FULL)

    assert total == 1
    assert [b.id for b in items] == [full.id]


def test_open_binders_still_excludes_handed_over(
    test_db, test_user, client_factory, binder_factory
):
    client = client_factory(full_name="A", id_number="OF-010")
    open_binder = _binder(
        binder_factory, test_db, client.id, test_user.id, "B-OPEN", date(2024, 1, 1)
    )
    handed = _binder(binder_factory, test_db, client.id, test_user.id, "B-HAND", date(2024, 1, 2))
    handed.location_status = BinderLocationStatus.HANDED_OVER
    test_db.commit()

    service = BinderOperationsService(test_db)
    # No filters: handed-over must remain excluded.
    items, total = service.get_open_binders()

    assert total == 1
    assert [b.id for b in items] == [open_binder.id]


def test_open_binders_handed_over_filter_does_not_widen_open_scope(
    test_db, test_user, client_factory, binder_factory
):
    client = client_factory(full_name="A", id_number="OF-011")
    _binder(binder_factory, test_db, client.id, test_user.id, "B-OPEN", date(2024, 1, 1))
    handed = _binder(binder_factory, test_db, client.id, test_user.id, "B-HAND", date(2024, 1, 2))
    handed.location_status = BinderLocationStatus.HANDED_OVER
    test_db.commit()

    service = BinderOperationsService(test_db)
    items, total = service.get_open_binders(location_status=BinderLocationStatus.HANDED_OVER)

    assert total == 0
    assert items == []


def test_open_binders_deterministic_tie_breaker(test_db, test_user, client_factory, binder_factory):
    client = client_factory(full_name="A", id_number="OF-012")
    # Same period_start → id tie-breaker (desc) decides order.
    first = _binder(binder_factory, test_db, client.id, test_user.id, "B-1", date(2024, 1, 1))
    second = _binder(binder_factory, test_db, client.id, test_user.id, "B-2", date(2024, 1, 1))

    service = BinderOperationsService(test_db)
    items, _total = service.get_open_binders()

    assert [b.id for b in items] == [second.id, first.id]
