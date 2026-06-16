from __future__ import annotations

from typing import Literal

from app.core.action_schemas import ActionDescriptor

ActionVariant = Literal["primary", "secondary", "danger"]


def link_action(
    key: str,
    label: str,
    route: str,
    *,
    primary: bool = False,
) -> ActionDescriptor:
    return ActionDescriptor(
        key=key,
        label=label,
        type="link",
        route=route,
        variant="primary" if primary else "secondary",
    )


def mutation_action(
    key: str,
    label: str,
    *,
    task_id: int | None = None,
    confirm_title: str | None = None,
    confirm_message: str | None = None,
    variant: ActionVariant = "secondary",
) -> ActionDescriptor:
    return ActionDescriptor(
        key=key,
        label=label,
        type="mutation",
        task_id=task_id,
        confirm=confirm_title is not None or confirm_message is not None,
        confirm_title=confirm_title,
        confirm_message=confirm_message,
        variant=variant,
    )


def modal_action(
    key: str,
    label: str,
    *,
    task_id: int | None = None,
    primary: bool = False,
    variant: ActionVariant | None = None,
) -> ActionDescriptor:
    return ActionDescriptor(
        key=key,
        label=label,
        type="modal",
        task_id=task_id,
        variant=variant or ("primary" if primary else "secondary"),
    )


__all__ = ["link_action", "mutation_action", "modal_action"]
