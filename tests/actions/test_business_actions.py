from types import SimpleNamespace

from app.actions.services.business_actions import get_business_actions
from app.businesses.models.business import BusinessStatus
from app.users.models.user import UserRole


def test_active_business_requires_explicit_advisor_role_for_actions():
    business = SimpleNamespace(id=5, status=BusinessStatus.ACTIVE)

    assert get_business_actions(business, user_role=None) == []
    assert get_business_actions(business, user_role=UserRole.SECRETARY) == []


def test_active_business_advisor_gets_freeze_and_close_actions():
    business = SimpleNamespace(id=5, status=BusinessStatus.ACTIVE)

    actions = get_business_actions(business, user_role=UserRole.ADVISOR)

    assert [action.key for action in actions] == ["freeze", "close"]


def test_frozen_business_advisor_gets_activate_and_close_actions():
    business = SimpleNamespace(id=7, status=BusinessStatus.FROZEN)

    actions = get_business_actions(business, user_role=UserRole.ADVISOR)

    assert [action.key for action in actions] == ["activate", "close"]


def test_frozen_business_secretary_only_gets_activate_action():
    business = SimpleNamespace(id=7, status=BusinessStatus.FROZEN)

    actions = get_business_actions(business, user_role=UserRole.SECRETARY)

    assert [action.key for action in actions] == ["activate"]
