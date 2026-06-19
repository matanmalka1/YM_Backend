from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.binders.models.binder import BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from tests.helpers.identity import seed_client_identity


def _user(test_db):
    user = User(
        full_name="Binder Unique Admin",
        email="binder.unique@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _client(test_db, name: str, id_number: str):
    return seed_client_identity(test_db, full_name=name, id_number=id_number)


def test_binder_number_is_unique_per_client_across_statuses(test_db):
    repo = BinderRepository(test_db)
    user = _user(test_db)
    client = _client(test_db, "Binder Unique", "BU001")

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


def test_binder_number_can_repeat_for_different_clients(test_db):
    repo = BinderRepository(test_db)
    user = _user(test_db)
    client_a = _client(test_db, "Binder Unique A", "BU002")
    client_b = _client(test_db, "Binder Unique B", "BU003")

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
