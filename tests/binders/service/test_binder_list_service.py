from datetime import date, timedelta

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.services.binder_list_service import BinderListService
from tests.helpers.identity import seed_client_identity


def _seed_binders(db, user_id: int):
    c1 = seed_client_identity(db, full_name="Alpha Client", id_number="BLS001")
    c2 = seed_client_identity(db, full_name="Beta Client", id_number="BLS002")

    b1 = Binder(
        client_record_id=c1.id,
        binder_number="AA-100",
        period_start=date.today() - timedelta(days=15),
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=user_id,
    )
    b2 = Binder(
        client_record_id=c2.id,
        binder_number="BB-200",
        period_start=date.today() - timedelta(days=5),
        location_status=BinderLocationStatus.READY_FOR_HANDOVER,
        capacity_status=BinderCapacityStatus.FULL,
        created_by=user_id,
    )
    db.add_all([b1, b2])
    db.commit()
    db.refresh(b1)
    db.refresh(b2)
    return c1, c2, b1, b2


def test_list_binders_enriched_filters_and_counters_use_lifecycle_fields(test_db, test_user):
    _c1, _c2, _b1, _b2 = _seed_binders(test_db, test_user.id)
    service = BinderListService(test_db)

    items, total, counters = service.list_binders_enriched(
        sort_by="client_name",
        order="invalid",
        query="AA",
        client_name_filter="alpha",
        binder_number="AA",
        year=date.today().year,
        page=1,
        page_size=10,
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].client_name == "Alpha Client"
    assert counters == {
        "total": 1,
        "location_in_office": 1,
        "location_ready_for_handover": 0,
        "location_handed_over": 0,
        "capacity_open": 1,
        "capacity_full": 0,
    }


def test_list_binders_enriched_excludes_handed_over_by_default(test_db, test_user):
    c1, _c2, b1, b2 = _seed_binders(test_db, test_user.id)
    handed_over = Binder(
        client_record_id=c1.id,
        binder_number="AA-300",
        period_start=date.today() - timedelta(days=1),
        location_status=BinderLocationStatus.HANDED_OVER,
        capacity_status=BinderCapacityStatus.FULL,
        handed_over_at=date.today(),
        created_by=test_user.id,
    )
    test_db.add(handed_over)
    test_db.commit()

    service = BinderListService(test_db)

    items, total, counters = service.list_binders_enriched()

    assert total == 2
    assert {item.id for item in items} == {b1.id, b2.id}
    assert counters["total"] == 3
    assert counters["location_handed_over"] == 1


def test_list_binders_enriched_location_filter_includes_handed_over(test_db, test_user):
    c1, _c2, _b1, _b2 = _seed_binders(test_db, test_user.id)
    handed_over = Binder(
        client_record_id=c1.id,
        binder_number="AA-400",
        period_start=date.today(),
        location_status=BinderLocationStatus.HANDED_OVER,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
    )
    test_db.add(handed_over)
    test_db.commit()

    service = BinderListService(test_db)
    items, total, _ = service.list_binders_enriched(location_status="handed_over")

    assert total == 1
    assert items[0].id == handed_over.id
    assert items[0].location_status == BinderLocationStatus.HANDED_OVER


def test_build_binder_response_handles_null_period_start(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Null Period Client", id_number="BLSNULL")
    binder = Binder(
        client_record_id=client.id,
        binder_number="NULL-100",
        period_start=None,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
    )
    test_db.add(binder)
    test_db.commit()
    test_db.refresh(binder)

    response = BinderListService(test_db).build_binder_response(
        binder,
        client_name=client.full_name,
    )

    assert response.period_start is None
    assert response.days_in_office is None
    assert response.available_actions == [
        "mark_ready_for_handover",
        "receive_material",
        "mark_full",
    ]
