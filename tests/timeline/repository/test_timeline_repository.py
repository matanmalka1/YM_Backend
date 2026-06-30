from datetime import date
from itertools import count

from app.binders.models.binder import Binder
from app.binders.repositories.binder_repository import BinderRepository
from app.users.models.user import User, UserRole
from tests.factories import create_user
from tests.helpers.identity import SeededClient, seed_client_identity

_client_seq = count(1)


def _client(db) -> SeededClient:
    idx = next(_client_seq)
    return seed_client_identity(
        db,
        full_name=f"Timeline Repo Client {idx}",
        id_number=f"TLR{idx:03d}",
    )


def _user(test_db) -> User:
    user = create_user(
        test_db,
        full_name="Timeline Repo User",
        email="timeline.repo@example.com",
        password="pass",
        role=UserRole.ADVISOR,
        is_active=True,
        commit=True,
    )
    return user


def test_list_client_binders_returns_only_requested_client_binders(test_db):
    user = _user(test_db)
    client_a = _client(test_db)
    client_b = _client(test_db)

    binder_repo = BinderRepository(test_db)
    b1 = Binder(
        client_record_id=client_a.id,
        binder_number="TL-B-001",
        period_start=date.today(),
        created_by=user.id,
    )
    b2 = Binder(
        client_record_id=client_a.id,
        binder_number="TL-B-002",
        period_start=date.today(),
        created_by=user.id,
    )
    b3 = Binder(
        client_record_id=client_b.id,
        binder_number="TL-B-003",
        period_start=date.today(),
        created_by=user.id,
    )
    test_db.add_all([b1, b2, b3])
    test_db.commit()

    result = binder_repo.list_by_client_record(client_a.id)

    assert {binder.id for binder in result} == {b1.id, b2.id}
