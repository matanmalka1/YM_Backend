from __future__ import annotations

from app.core.action_builders import mutation_action
from app.core.action_schemas import ActionDescriptor
from app.users.models.user import UserRole
from app.vat_reports.models.vat_enums import VatWorkItemStatus
from app.vat_reports.models.vat_work_item import VatWorkItem


def _is_advisor(user_role: UserRole | str | None) -> bool:
    return user_role in (UserRole.ADVISOR, UserRole.ADVISOR.value)


def get_vat_work_item_actions(
    item: VatWorkItem,
    *,
    user_role: UserRole | str | None = None,
) -> list[ActionDescriptor]:
    """Return executable actions for a VAT work item."""
    status = item.status
    actions: list[ActionDescriptor] = []

    if status == VatWorkItemStatus.PENDING_MATERIALS:
        actions.append(
            mutation_action(
                key="materials_complete",
                label="אישור קבלת חומרים",
                endpoint=f"/vat/work-items/{item.id}/materials-complete",
            )
        )

    if status in {
        VatWorkItemStatus.MATERIAL_RECEIVED,
        VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
        VatWorkItemStatus.READY_FOR_REVIEW,
    }:
        actions.append(
            mutation_action(
                key="add_invoice",
                label="הוספת חשבונית",
                endpoint=f"/vat/work-items/{item.id}/invoices",
            )
        )

    if status == VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS:
        actions.append(
            mutation_action(
                key="ready_for_review",
                label="שלח לבדיקה",
                endpoint=f"/vat/work-items/{item.id}/ready-for-review",
            )
        )

    if _is_advisor(user_role) and status == VatWorkItemStatus.READY_FOR_REVIEW:
        actions.extend(
            [
                mutation_action(
                    key="file_vat_return",
                    label='הגש מע"מ',
                    endpoint=f"/vat/work-items/{item.id}/file",
                ),
                mutation_action(
                    key="send_back",
                    label="החזר לתיקון",
                    endpoint=f"/vat/work-items/{item.id}/send-back",
                    confirm_title="החזרה לתיקון",
                    confirm_message="יש לציין הערה לפני החזרת התיק לתיקון.",
                ),
            ]
        )

    return actions


__all__ = ["get_vat_work_item_actions"]
