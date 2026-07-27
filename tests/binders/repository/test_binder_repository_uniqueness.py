from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.binders.models.binder import BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository


def test_binder_number_is_unique_per_client_across_statuses(test_db, user_factory, client_factory):
    repo = BinderRepository(test_db)
    user = user_factory()
    client = client_factory(full_name="Binder Unique", id_number="BU001")

    handed_over = repo.create(
        client_record_id=client.id,
        binder_number="BU-1",
        period_start=date(2024, 1, 1),
        created_by=user.id,
    )
    handed_over.location_status = BinderLocationStatus.HANDED_OVER
    test_db.flush()

    with pytest.raises(IntegrityError):
        repo.create(
            client_record_id=client.id,
            binder_number="BU-1",
            period_start=date(2024, 2, 1),
            created_by=user.id,
        )


def test_binder_number_can_repeat_for_different_clients(test_db, user_factory, client_factory):
    repo = BinderRepository(test_db)
    user = user_factory()
    client_a = client_factory(full_name="Binder Unique A", id_number="BU002")
    client_b = client_factory(full_name="Binder Unique B", id_number="BU003")

    first = repo.create(
        client_record_id=client_a.id,
        binder_number="SHARED-1",
        period_start=date(2024, 1, 1),
        created_by=user.id,
    )
    second = repo.create(
        client_record_id=client_b.id,
        binder_number="SHARED-1",
        period_start=date(2024, 2, 1),
        created_by=user.id,
    )

    assert first.id != second.id
