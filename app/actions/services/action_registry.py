"""Action registry: aggregates domain action factories. Import from here, not individual modules."""

from app.actions.services.binder_actions import get_binder_actions, get_binder_actions_for_state
from app.actions.services.charge_actions import get_charge_actions
from app.actions.services.report_deadline_actions import get_annual_report_actions
from app.actions.services.vat_report_actions import get_vat_work_item_actions

__all__ = [
    "get_binder_actions",
    "get_binder_actions_for_state",
    "get_charge_actions",
    "get_annual_report_actions",
    "get_vat_work_item_actions",
]
