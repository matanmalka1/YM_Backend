from app.actions.services.report_deadline_actions import get_annual_report_actions
from app.annual_reports.models.annual_report_enums import AnnualReportStatus


def test_get_annual_report_actions_submitted_has_amend_only():
    actions = get_annual_report_actions(status=AnnualReportStatus.SUBMITTED.value)

    assert [action.key for action in actions] == ["amend"]


def test_get_annual_report_actions_open_status_has_submit():
    actions = get_annual_report_actions(status=AnnualReportStatus.IN_PREPARATION.value)

    assert [action.key for action in actions] == ["submit"]


def test_get_annual_report_actions_closed_states_have_no_actions():
    statuses = [
        AnnualReportStatus.CLOSED.value,
        AnnualReportStatus.CANCELED.value,
    ]

    for state in statuses:
        assert get_annual_report_actions(status=state) == []
