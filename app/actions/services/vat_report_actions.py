from __future__ import annotations

from app.common.enums import ObligationStatus
from app.core.action_builders import mutation_action
from app.core.action_schemas import ActionDescriptor
from app.users.models.user import UserRole
from app.vat.models.vat_work_item import VatWorkItem


def _is_advisor(user_role: UserRole | str | None) -> bool:
    return user_role in (UserRole.ADVISOR, UserRole.ADVISOR.value)


def get_vat_work_item_actions(
    item: VatWorkItem,
    *,
    user_role: UserRole | str | None = None,
) -> list[ActionDescriptor]:
    """Return available actions for a VAT work item."""
    status = item.status
    actions: list[ActionDescriptor] = []

    if status == ObligationStatus.AWAITING_INPUT:
        actions.append(
            mutation_action(
                key="materials_complete",
                label="אישור קבלת חומרים",
            )
        )

    if status in {
        ObligationStatus.INPUT_RECEIVED,
        ObligationStatus.IN_PROGRESS,
        ObligationStatus.AWAITING_VERIFICATION,
    }:
        actions.append(
            mutation_action(
                key="add_invoice",
                label="הוספת חשבונית",
            )
        )

    if status == ObligationStatus.IN_PROGRESS:
        actions.append(
            mutation_action(
                key="ready_for_review",
                label="שלח לבדיקה",
            )
        )

    if _is_advisor(user_role) and status == ObligationStatus.AWAITING_VERIFICATION:
        actions.extend(
            [
                mutation_action(
                    key="file_vat_return",
                    label='הגש מע"מ',
                ),
                mutation_action(
                    key="send_back",
                    label="החזר לתיקון",
                    confirm_title="החזרה לתיקון",
                    confirm_message="יש לציין הערה לפני החזרת התיק לתיקון.",
                ),
            ]
        )

    return actions


__all__ = ["get_vat_work_item_actions"]
