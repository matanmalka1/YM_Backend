from datetime import date, timedelta

from app.binders.models.binder import BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.users.models.user import UserRole
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_identity


def _user(user_factory):
    return user_factory(
        full_name="Handover Query User",
        email="handover.query@example.com",
        password="pass",
        role=UserRole.ADVISOR,
        is_active=True,
        commit=False,
    )


def _binder(repo, client_id: int, user_id: int, number: str, days_waiting: int, location_status):
    binder = repo.create(
        client_record_id=client_id,
        binder_number=number,
        period_start=date(2026, 1, 1),
        created_by=user_id,
    )
    binder.location_status = location_status
    binder.ready_for_handover_at = utcnow() - timedelta(days=days_waiting)
    return binder


def test_list_overdue_handover_returns_only_old_ready_binders(test_db, user_factory):
    repo = BinderRepository(test_db)
    user = _user(user_factory)
    client = seed_client_identity(test_db, full_name="Handover Client", id_number="HAND001")
    old_ready = _binder(
        repo, client.id, user.id, "HAND-1", 40, BinderLocationStatus.READY_FOR_HANDOVER
    )
    _binder(repo, client.id, user.id, "HAND-2", 10, BinderLocationStatus.READY_FOR_HANDOVER)
    _binder(repo, client.id, user.id, "HAND-3", 45, BinderLocationStatus.IN_OFFICE)
    deleted = _binder(
        repo, client.id, user.id, "HAND-4", 50, BinderLocationStatus.READY_FOR_HANDOVER
    )
    deleted.deleted_at = utcnow()
    test_db.commit()

    result = repo.list_overdue_handover(overdue_days=30, limit=10)

    assert [binder.id for binder in result] == [old_ready.id]
