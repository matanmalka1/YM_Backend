from __future__ import annotations

from app.charges.models.charge import Charge, ChargeStatus
from app.core.action_builders import modal_action, mutation_action
from app.core.action_schemas import ActionDescriptor
from app.users.models.user import UserRole


def _cancel_charge_action() -> ActionDescriptor:
    return mutation_action(
        key="cancel_charge",
        label="ביטול חיוב",
        confirm_title="אישור ביטול חיוב",
        confirm_message="האם לבטל את החיוב?",
        variant="danger",
    )


def _delete_charge_action() -> ActionDescriptor:
    return mutation_action(
        key="delete_charge",
        label="מחיקת חיוב",
        confirm_title="מחיקת חיוב",
        confirm_message="האם למחוק את החיוב?",
        variant="danger",
    )


def get_charge_actions(
    charge: Charge,
    user_role: UserRole | None = None,
) -> list[ActionDescriptor]:
    if user_role is not None and user_role not in (UserRole.ADVISOR, UserRole.SECRETARY):
        return []

    status = charge.status
    actions: list[ActionDescriptor] = []

    if status == ChargeStatus.DRAFT:
        actions.append(modal_action(key="edit_charge", label="עריכת חיוב"))
        actions.append(
            mutation_action(
                key="issue_charge",
                label="הוצאת חיוב",
            )
        )
        actions.append(_cancel_charge_action())

    if status == ChargeStatus.ISSUED:
        actions.append(
            mutation_action(
                key="mark_paid",
                label="סימון חיוב כשולם",
                confirm_title="אישור סימון חיוב כשולם",
                confirm_message="האם לסמן את החיוב כשולם?",
            )
        )
        actions.append(_cancel_charge_action())

    # Mirrors BillingService.delete_charge, which allows soft-delete from draft or canceled.
    if status in (ChargeStatus.DRAFT, ChargeStatus.CANCELED):
        actions.append(_delete_charge_action())

    return actions


__all__ = ["get_charge_actions"]
