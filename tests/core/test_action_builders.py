from app.core.action_builders import link_action, modal_action, mutation_action


def test_mutation_action_builds_defaults_and_confirmation_variants():
    default = mutation_action("cancel", "ביטול", "/things/1/cancel")
    confirmed = mutation_action(
        "delete",
        "מחק",
        "/things/1",
        confirm_title="אישור",
        confirm_message="?",
        variant="danger",
        payload_schema="requires_input",
    )

    assert default.model_dump(exclude_none=True) == {
        "key": "cancel",
        "label": "ביטול",
        "type": "mutation",
        "endpoint": "/things/1/cancel",
        "method": "post",
        "confirm": False,
        "variant": "secondary",
        "payload_schema": "none",
        "disabled": False,
    }
    assert confirmed.confirm is True
    assert confirmed.confirm_title == "אישור"
    assert confirmed.confirm_message == "?"
    assert confirmed.variant == "danger"
    assert confirmed.payload_schema == "requires_input"


def test_link_action_builds_route_and_primary_variant():
    action = link_action("open", "פתח", "/clients/5", primary=True)

    assert action.type == "link"
    assert action.route == "/clients/5"
    assert action.endpoint is None
    assert action.variant == "primary"


def test_modal_action_builds_task_and_primary_variant():
    action = modal_action("edit", "ערוך", task_id=3, primary=True)

    assert action.type == "modal"
    assert action.task_id == 3
    assert action.variant == "primary"
