from types import SimpleNamespace

from app.actions.services.binder_actions import get_binder_actions
from app.binders.models.binder import BinderCapacityStatus, BinderLocationStatus


def _binder(location_status, capacity_status):
    return SimpleNamespace(
        id=10,
        location_status=location_status,
        capacity_status=capacity_status,
    )


def test_intake_eligible_binder_exposes_receive_capacity_and_handover_actions():
    binder = _binder(BinderLocationStatus.IN_OFFICE, BinderCapacityStatus.OPEN)

    actions = get_binder_actions(binder)

    assert actions == ["mark_ready_for_handover", "receive_material", "mark_full"]


def test_full_in_office_binder_exposes_reopen_and_handover_actions():
    binder = _binder(BinderLocationStatus.IN_OFFICE, BinderCapacityStatus.FULL)

    assert get_binder_actions(binder) == ["mark_ready_for_handover", "reopen_capacity"]


def test_ready_for_handover_binder_exposes_revert_and_handover_actions():
    binder = _binder(BinderLocationStatus.READY_FOR_HANDOVER, BinderCapacityStatus.FULL)

    assert get_binder_actions(binder) == ["revert_ready_for_handover", "handover_to_client"]


def test_handed_over_binder_has_no_actions():
    binder = _binder(BinderLocationStatus.HANDED_OVER, BinderCapacityStatus.FULL)

    assert get_binder_actions(binder) == []
