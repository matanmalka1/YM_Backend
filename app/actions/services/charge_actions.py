from __future__ import annotations

from app.charge.models.charge import Charge, ChargeStatus
from app.core.action_builders import mutation_action
from app.core.action_schemas import ActionDescriptor
from app.users.models.user import UserRole


def _cancel_charge_action(charge_id: int) -> ActionDescriptor:
    return mutation_action(
        key="cancel_charge",
        label="ביטול חיוב",
        endpoint=f"/charges/{charge_id}/cancel",
        confirm_title="אישור ביטול חיוב",
        confirm_message="האם לבטל את החיוב?",
        variant="danger",
    )


def get_charge_actions(
    charge: Charge,
    user_role: UserRole | None = None,
) -> list[ActionDescriptor]:
    if user_role is not None and user_role != UserRole.ADVISOR:
        return []

    status = charge.status
    actions: list[ActionDescriptor] = []

    if status == ChargeStatus.DRAFT:
        actions.append(
            mutation_action(
                key="issue_charge",
                label="הוצאת חיוב",
                endpoint=f"/charges/{charge.id}/issue",
            )
        )
        actions.append(_cancel_charge_action(charge.id))
        actions.append(
            mutation_action(
                key="delete_charge",
                label="מחיקת חיוב",
                method="delete",
                endpoint=f"/charges/{charge.id}",
                confirm_title="מחיקת חיוב",
                confirm_message="האם למחוק את החיוב?",
                variant="danger",
            )
        )

    if status == ChargeStatus.ISSUED:
        actions.append(
            mutation_action(
                key="mark_paid",
                label="סימון חיוב כשולם",
                endpoint=f"/charges/{charge.id}/mark-paid",
                confirm_title="אישור סימון חיוב כשולם",
                confirm_message="האם לסמן את החיוב כשולם?",
            )
        )
        actions.append(_cancel_charge_action(charge.id))

    return actions


__all__ = ["get_charge_actions"]
