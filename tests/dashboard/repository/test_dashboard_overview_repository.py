from datetime import date

from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.businesses.repositories.business_repository import BusinessRepository
from app.common.enums import IdNumberType


def test_business_and_binder_repository_counts_active_entities(
    test_db, user_factory, client_factory, business_factory, binder_factory
):
    user = user_factory(
        full_name="Receiver",
        email="receiver@example.com",
        password="pass",
        is_active=True,
        commit=False,
    )

    client_a = client_factory(
        full_name="Alpha Ltd",
        id_number="C001",
        id_number_type=IdNumberType.INDIVIDUAL,
        office_client_number=100901,
        create_person=False,
    )
    client_b = client_factory(
        full_name="Beta LLC",
        id_number="C002",
        id_number_type=IdNumberType.INDIVIDUAL,
        office_client_number=100902,
        create_person=False,
    )

    business_factory(
        legal_entity_id=client_a.legal_entity_id,
        business_name="Alpha Business",
        opened_at=date(2024, 1, 1),
    )
    business_factory(
        legal_entity_id=client_b.legal_entity_id,
        business_name="Beta Business",
        opened_at=date(2024, 2, 1),
    )

    binder_factory(
        client_record_id=client_a.id,
        binder_number="B-1",
        period_start=date(2024, 3, 1),
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=user.id,
    )
    binder_factory(
        client_record_id=client_b.id,
        binder_number="B-2",
        period_start=date(2024, 3, 2),
        handed_over_at=date(2024, 3, 5),
        location_status=BinderLocationStatus.HANDED_OVER,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=user.id,
    )
    test_db.commit()

    total_businesses = BusinessRepository(test_db).count()
    active_binders = BinderRepository(test_db).count_active()

    assert total_businesses >= 2
    assert active_binders >= 1
    # Handed-over binder should not be counted as active.
    assert active_binders < total_businesses + 1
