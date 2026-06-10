from types import SimpleNamespace

from app.actions.services.business_actions import get_business_actions
from app.actions.services.charge_actions import get_charge_actions
from app.actions.services.report_deadline_actions import get_annual_report_actions
from app.actions.services.vat_report_actions import get_vat_work_item_actions
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.businesses.models.business import BusinessStatus
from app.charge.models.charge import ChargeStatus
from app.core.action_serialization import dump_action_descriptor
from app.users.models.user import UserRole
from app.vat_reports.models.vat_enums import VatWorkItemStatus


def test_charge_cancel_serializes_correct_frontend_shape():
    charge = SimpleNamespace(id=20, status=ChargeStatus.DRAFT)

    actions = get_charge_actions(charge)
    cancel = next(action for action in actions if action.key == "cancel_charge")
    dumped = dump_action_descriptor(cancel)

    assert dumped["confirm_title"] == "אישור ביטול חיוב"
    assert dumped["variant"] == "danger"
    assert "confirm_label" not in dumped


def test_business_freeze_serializes_payload_schema():
    business = SimpleNamespace(id=5, client_id=9, status=BusinessStatus.ACTIVE)

    actions = get_business_actions(business, user_role=UserRole.ADVISOR)
    freeze = next(action for action in actions if action.key == "freeze")
    dumped = dump_action_descriptor(freeze)

    assert dumped["payload_schema"] == "simple"
    assert "payload" not in dumped


def test_vat_send_back_serializes_confirm():
    item = SimpleNamespace(id=3, status=VatWorkItemStatus.READY_FOR_REVIEW)

    actions = get_vat_work_item_actions(item, user_role=UserRole.ADVISOR)
    send_back = next(action for action in actions if action.key == "send_back")
    dumped = dump_action_descriptor(send_back)

    assert dumped["confirm"] is True
    assert dumped["confirm_title"] == "החזרה לתיקון"


def test_annual_report_submit_serializes_correct_endpoint():
    actions = get_annual_report_actions(
        report_id=8,
        status=AnnualReportStatus.NOT_STARTED.value,
    )
    submit = next(action for action in actions if action.key == "submit")
    dumped = dump_action_descriptor(submit)

    assert dumped["endpoint"] == "/annual-reports/8/submit"
    assert "id" not in dumped
