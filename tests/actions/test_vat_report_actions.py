from datetime import UTC, datetime
from types import SimpleNamespace

from app.actions.services.vat_report_actions import get_vat_work_item_actions
from app.common.enums import ObligationStatus
from app.users.models.user import UserRole


def _item(**overrides) -> SimpleNamespace:
    """A work item as the action builder sees it.

    The chain columns are part of the shape whether or not a test is about them:
    the builder reads them to decide whether a correction can be taken back, so a
    namespace without them is not a work item.
    """
    fields = {
        "id": 30,
        "status": ObligationStatus.AWAITING_VERIFICATION,
        "amends_id": None,
        "superseded_at": None,
        "deleted_at": None,
    }
    fields.update(overrides)
    return SimpleNamespace(
        is_amendment=fields["amends_id"] is not None,
        is_withdrawn=fields["amends_id"] is not None and fields["deleted_at"] is not None,
        **fields,
    )


def _amendment(**overrides) -> SimpleNamespace:
    """An open correction."""
    return _item(**{"id": 40, "status": ObligationStatus.IN_PROGRESS, "amends_id": 39, **overrides})


def test_ready_for_review_advisor_actions():
    actions = get_vat_work_item_actions(_item(), user_role=UserRole.ADVISOR)

    assert [action.key for action in actions] == [
        "add_invoice",
        "file_vat_return",
        "send_back",
    ]


def test_ready_for_review_secretary_actions():
    actions = get_vat_work_item_actions(_item(id=31), user_role=UserRole.SECRETARY)

    assert [action.key for action in actions] == ["add_invoice"]


def test_an_open_amendment_offers_withdrawal_to_an_advisor():
    actions = get_vat_work_item_actions(_amendment(), user_role=UserRole.ADVISOR)

    assert "withdraw_amendment" in [action.key for action in actions]


def test_withdrawal_is_not_offered_on_an_original():
    actions = get_vat_work_item_actions(_amendment(amends_id=None), user_role=UserRole.ADVISOR)

    assert "withdraw_amendment" not in [action.key for action in actions]


def test_withdrawal_is_not_offered_to_a_secretary():
    """The route is advisor-only, so offering it to anyone else is a dead button."""
    actions = get_vat_work_item_actions(_amendment(), user_role=UserRole.SECRETARY)

    assert "withdraw_amendment" not in [action.key for action in actions]


def test_withdrawal_is_not_offered_on_a_filed_amendment():
    """A filed correction is the record of a filing (D-13)."""
    actions = get_vat_work_item_actions(
        _amendment(status=ObligationStatus.SUBMITTED), user_role=UserRole.ADVISOR
    )

    assert "withdraw_amendment" not in [action.key for action in actions]


def test_a_withdrawn_amendment_offers_nothing():
    """It is reachable from the chain history only, and nothing acts on it there."""
    actions = get_vat_work_item_actions(
        _amendment(deleted_at=datetime(2026, 7, 30, tzinfo=UTC)), user_role=UserRole.ADVISOR
    )

    assert actions == []


def test_a_canceled_amendment_still_offers_withdrawal():
    """Cancelling is terminal but it is not a filing, and withdrawing is the only
    way out of a period whose tip is a cancelled correction."""
    actions = get_vat_work_item_actions(
        _amendment(status=ObligationStatus.CANCELED), user_role=UserRole.ADVISOR
    )

    assert [action.key for action in actions] == ["withdraw_amendment"]
