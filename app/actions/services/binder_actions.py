from __future__ import annotations

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.services.binder_lifecycle_service import BinderLifecycleService


def get_binder_actions_for_state(
    *,
    location_status: BinderLocationStatus,
    capacity_status: BinderCapacityStatus,
) -> list[str]:
    return BinderLifecycleService.get_available_action_keys_for_state(
        location_status=location_status,
        capacity_status=capacity_status,
    )


def get_binder_actions(binder: Binder) -> list[str]:
    return BinderLifecycleService.get_available_action_keys(binder)


__all__ = ["get_binder_actions", "get_binder_actions_for_state"]
