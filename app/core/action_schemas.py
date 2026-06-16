from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ActionDescriptor(BaseModel):
    """Availability metadata: which action a resource currently exposes.

    Descriptors are NOT executable commands. The frontend reads ``key`` to know
    an action is available and routes it to a typed API client/hook; it never
    executes a descriptor-supplied endpoint/method/payload. The remaining fields
    are presentation/UX metadata consumed by the work-queue UI (label, type,
    route for link actions, confirm dialog text, variant, disabled state).
    Target endpoints/services remain the source of truth for authorization and
    business validation.
    """

    key: str
    label: str
    type: Literal["link", "mutation", "modal"]
    route: str | None = None
    task_id: int | None = None
    confirm: bool = False
    confirm_title: str | None = None
    confirm_message: str | None = None
    variant: Literal["primary", "secondary", "danger"] = "secondary"
    disabled: bool = False
    disabled_reason: str | None = None


__all__ = ["ActionDescriptor"]
