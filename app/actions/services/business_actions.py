from __future__ import annotations

from app.businesses.models.business import Business, BusinessStatus
from app.core.action_builders import mutation_action
from app.core.action_schemas import ActionDescriptor
from app.users.models.user import UserRole


def get_business_actions(
    business: Business,
    user_role: UserRole | None = None,
) -> list[ActionDescriptor]:
    """Return available actions for a business (role-aware)."""
    status = business.status
    actions: list[ActionDescriptor] = []

    if status == BusinessStatus.ACTIVE and user_role == UserRole.ADVISOR:
        actions.append(
            mutation_action(
                key="freeze",
                label="הקפאת עסק",
                confirm_title="אישור הקפאת עסק",
                confirm_message="האם להקפיא את העסק?",
            )
        )
        actions.append(
            mutation_action(
                key="close",
                label="סגירת עסק",
                confirm_title="אישור סגירת עסק",
                confirm_message="האם לסגור את העסק?",
            )
        )

    if status == BusinessStatus.FROZEN:
        actions.append(
            mutation_action(
                key="activate",
                label="הפעלת עסק",
            )
        )
        if user_role == UserRole.ADVISOR:
            actions.append(
                mutation_action(
                    key="close",
                    label="סגירת עסק",
                    confirm_title="אישור סגירת עסק",
                    confirm_message="האם לסגור את העסק?",
                )
            )

    return actions


__all__ = ["get_business_actions"]
