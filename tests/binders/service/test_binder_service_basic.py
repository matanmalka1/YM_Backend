from datetime import date

from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_service import BinderService
from tests.helpers.identity import SeededClient, seed_client_identity


def _create_client(db) -> SeededClient:
    return seed_client_identity(
        db,
        full_name="Binder Client",
        id_number="B-100",
    )


def _create_binder(db, client_id: int, user_id: int, number: str):
    repo = BinderRepository(db)
    return repo.create(
        client_record_id=client_id,
        binder_number=number,
        period_start=date(2024, 1, 10),
        created_by=user_id,
    )


def test_delete_binder_soft_deletes_and_returns_true(test_db, test_user):
    client = _create_client(test_db)
    binder = _create_binder(test_db, client.id, test_user.id, "BIN-002")
    service = BinderService(test_db)

    deleted = service.delete_binder(binder.id, actor_id=test_user.id)

    assert deleted is True
    assert BinderRepository(test_db).get_by_id(binder.id) is None


def test_delete_binder_missing_returns_false(test_db, actor_user):
    service = BinderService(test_db)

    assert service.delete_binder(999, actor_id=actor_user.id) is False
