from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

HttpMethod = Literal["get", "post", "put", "patch", "delete"]


class ConfirmInput(TypedDict):
    name: str
    label: str
    type: Literal["text"]
    required: bool


class ActionConfirm(TypedDict):
    title: str
    message: str
    confirm_label: str
    cancel_label: str
    inputs: NotRequired[list[ConfirmInput]]


_VALID_METHODS = {"get", "post", "put", "patch", "delete"}


def build_confirm(
    title: str,
    message: str,
    *,
    confirm_label: str = "אישור",
    cancel_label: str = "ביטול",
    inputs: list[ConfirmInput] | None = None,
) -> ActionConfirm:
    confirm: ActionConfirm = {
        "title": title,
        "message": message,
        "confirm_label": confirm_label,
        "cancel_label": cancel_label,
    }
    if inputs is not None:
        confirm["inputs"] = inputs
    return confirm


def build_action(
    key: str,
    label: str,
    method: HttpMethod,
    endpoint: str,
    action_id: str,
    payload: dict[str, Any] | None = None,
    confirm: ActionConfirm | None = None,
) -> dict[str, Any]:
    if method not in _VALID_METHODS:
        raise ValueError("Action method is not supported")
    action: dict[str, Any] = {
        "id": action_id,
        "key": key,
        "label": label,
        "method": method,
        "endpoint": endpoint,
    }

    if payload is not None:
        action["payload"] = payload

    if confirm is not None:
        action["confirm"] = confirm

    return action


__all__ = [
    "ActionConfirm",
    "ConfirmInput",
    "HttpMethod",
    "build_action",
    "build_confirm",
]
