from types import SimpleNamespace

from app.actions.services.vat_report_actions import get_vat_work_item_actions
from app.users.models.user import UserRole
from app.vat.models.vat_enums import VatWorkItemStatus


def test_ready_for_review_advisor_actions():
    item = SimpleNamespace(id=30, status=VatWorkItemStatus.READY_FOR_REVIEW)

    actions = get_vat_work_item_actions(item, user_role=UserRole.ADVISOR)

    assert [action.key for action in actions] == [
        "add_invoice",
        "file_vat_return",
        "send_back",
    ]


def test_ready_for_review_secretary_actions():
    item = SimpleNamespace(id=31, status=VatWorkItemStatus.READY_FOR_REVIEW)

    actions = get_vat_work_item_actions(item, user_role=UserRole.SECRETARY)

    assert [action.key for action in actions] == ["add_invoice"]
