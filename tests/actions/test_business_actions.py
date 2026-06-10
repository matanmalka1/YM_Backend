from types import SimpleNamespace

from app.actions.services.business_actions import get_business_actions
from app.businesses.models.business import BusinessStatus
from app.users.models.user import UserRole


def test_active_business_requires_explicit_advisor_role_for_actions():
    business = SimpleNamespace(id=5, client_id=9, status=BusinessStatus.ACTIVE)

    assert get_business_actions(business, user_role=None) == []
    assert get_business_actions(business, user_role=UserRole.SECRETARY) == []


def test_active_business_advisor_gets_freeze_and_close_actions():
    business = SimpleNamespace(id=5, client_id=9, status=BusinessStatus.ACTIVE)

    actions = get_business_actions(business, user_role=UserRole.ADVISOR)

    assert [action.key for action in actions] == ["freeze", "close"]
    assert actions[0].payload_schema == "simple"
    assert actions[1].payload_schema == "simple"
    assert actions[0].endpoint == "/clients/9/businesses/5"


def test_frozen_business_advisor_gets_activate_and_close_actions():
    business = SimpleNamespace(id=7, client_id=9, status=BusinessStatus.FROZEN)

    actions = get_business_actions(business, user_role=UserRole.ADVISOR)

    assert [action.key for action in actions] == ["activate", "close"]
    assert actions[0].payload_schema == "simple"
    assert actions[1].payload_schema == "simple"
    assert actions[0].endpoint == "/clients/9/businesses/7"


def test_frozen_business_secretary_only_gets_activate_action():
    business = SimpleNamespace(id=7, client_id=9, status=BusinessStatus.FROZEN)

    actions = get_business_actions(business, user_role=UserRole.SECRETARY)

    assert [action.key for action in actions] == ["activate"]


def test_business_actions_uses_client_id_even_when_legal_entity_id_exists():
    business = SimpleNamespace(
        id=8,
        client_id=9,
        legal_entity_id=77,
        status=BusinessStatus.ACTIVE,
    )

    actions = get_business_actions(business, user_role=UserRole.ADVISOR)

    assert actions[0].endpoint == "/clients/9/businesses/8"


def test_business_actions_raises_when_client_id_missing():
    business = SimpleNamespace(id=8, legal_entity_id=77, status=BusinessStatus.ACTIVE)

    try:
        get_business_actions(business, user_role=UserRole.ADVISOR)
        assert False, "Expected ValueError when client_id is missing"
    except ValueError as exc:
        assert str(exc) == "Business actions require client_id for endpoint construction"
