from datetime import date

import pytest

from app.audit.audit_constants import (
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_MATERIAL_RECEIVED,
    ACTION_BINDER_REOPENED,
    ENTITY_BINDER,
)
from app.audit.repositories.audit_entity_audit_log_repository import (
    EntityAuditLogRepository,
)
from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus
from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.core.exceptions import AppError
from tests.helpers.identity import seed_client_identity


def _binder_actions(db, binder_id: int) -> list[str]:
    """Lifecycle actions recorded for a binder, oldest first."""
    rows = EntityAuditLogRepository(db).list_by_entity(ENTITY_BINDER, binder_id)
    return [row.action for row in reversed(rows)]


def _binder(db, client_id: int, user_id: int):
    return BinderRepository(db).create(
        client_record_id=client_id,
        binder_number="LC-1",
        period_start=date(2026, 1, 1),
        created_by=user_id,
    )


def test_mark_full_reopen_and_handover_transitions_write_lifecycle_logs(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Lifecycle Client", id_number="LC-100")
    binder = _binder(test_db, client.id, test_user.id)
    service = BinderLifecycleService(test_db)

    full = service.mark_full(binder.id, changed_by_user_id=test_user.id)
    assert full.location_status == BinderLocationStatus.IN_OFFICE
    assert full.capacity_status == BinderCapacityStatus.FULL

    reopened = service.reopen_capacity(binder.id, changed_by_user_id=test_user.id)
    assert reopened.capacity_status == BinderCapacityStatus.OPEN

    ready, _notif = service.mark_ready_for_handover(binder.id, changed_by_user_id=test_user.id)
    assert ready.location_status == BinderLocationStatus.READY_FOR_HANDOVER
    assert ready.capacity_status == BinderCapacityStatus.OPEN

    handed_over = service.handover_to_client(
        binder.id,
        changed_by_user_id=test_user.id,
        handed_over_at=date(2026, 2, 1),
        handover_recipient_name="Dana",
    )
    assert handed_over.location_status == BinderLocationStatus.HANDED_OVER
    assert handed_over.handed_over_at == date(2026, 2, 1)
    assert handed_over.handover_recipient_name == "Dana"

    assert _binder_actions(test_db, binder.id) == [
        ACTION_BINDER_MARKED_FULL,
        ACTION_BINDER_REOPENED,
        ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
        ACTION_BINDER_HANDED_OVER,
    ]


def test_lifecycle_errors_use_fixed_domain_codes(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Lifecycle Error Client", id_number="LC-101")
    binder = _binder(test_db, client.id, test_user.id)
    service = BinderLifecycleService(test_db)

    with pytest.raises(AppError) as already_open:
        service.reopen_capacity(binder.id, changed_by_user_id=test_user.id)
    assert already_open.value.code == "BINDER.NOT_FULL"

    service.mark_ready_for_handover(binder.id, changed_by_user_id=test_user.id)  # noqa: RET504 — side effects only

    with pytest.raises(AppError) as capacity_blocked:
        service.mark_full(binder.id, changed_by_user_id=test_user.id)
    assert capacity_blocked.value.code == "BINDER.CAPACITY_CHANGE_NOT_ALLOWED"

    service.handover_to_client(binder.id, changed_by_user_id=test_user.id)

    with pytest.raises(AppError) as already_handed:
        service.handover_to_client(binder.id, changed_by_user_id=test_user.id)
    assert already_handed.value.code == "BINDER.ALREADY_HANDED_OVER"


def test_receive_material_writes_audit_log_without_state_change(test_db, test_user):
    client = seed_client_identity(test_db, full_name="Lifecycle Receive Client", id_number="LC-102")
    binder = _binder(test_db, client.id, test_user.id)
    service = BinderLifecycleService(test_db)

    received = service.receive_material(binder, changed_by_user_id=test_user.id)

    assert received.location_status == BinderLocationStatus.IN_OFFICE
    assert received.capacity_status == BinderCapacityStatus.OPEN
    assert _binder_actions(test_db, binder.id) == [ACTION_BINDER_MATERIAL_RECEIVED]


def test_audit_failure_rolls_back_binder_lifecycle_mutation(test_db, test_user, monkeypatch):
    """A failing audit write rolls back the binder lifecycle mutation in the same
    transaction (§17) — the binder's status change does not persist and no audit row lands."""
    from app.core.error_codes import ErrorCode

    client = seed_client_identity(test_db, full_name="Atomic Binder", id_number="LC-ATOMIC")
    binder = _binder(test_db, client.id, test_user.id)
    service = BinderLifecycleService(test_db)

    def _boom(*args, **kwargs):
        raise AppError("forced audit failure", ErrorCode.AUDIT_FORBIDDEN_FIELD, status_code=500)

    # Force the audit append to fail mid-transition.
    monkeypatch.setattr(service.audit_writer, "record_action", _boom)

    with pytest.raises(AppError):
        with test_db.begin_nested():
            service.mark_full(binder.id, changed_by_user_id=test_user.id)

    test_db.expire_all()
    reloaded = BinderRepository(test_db).get_by_id(binder.id)
    assert reloaded.capacity_status == BinderCapacityStatus.OPEN
    assert _binder_actions(test_db, binder.id) == []
