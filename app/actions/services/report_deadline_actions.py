"""Action contracts for annual reports."""

from __future__ import annotations

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.core.action_builders import mutation_action
from app.core.action_schemas import ActionDescriptor

SUBMIT_BLOCKED_STATUSES = {
    AnnualReportStatus.SUBMITTED.value,
    AnnualReportStatus.CLOSED.value,
    AnnualReportStatus.CANCELED.value,
}


def get_annual_report_actions(report_id: int, status: str) -> list[ActionDescriptor]:
    """Return executable actions for an annual report based on its status."""
    actions: list[ActionDescriptor] = []

    if status == AnnualReportStatus.SUBMITTED.value:
        actions.append(
            mutation_action(
                key="amend",
                label="תיקון דוח",
                endpoint=f"/annual-reports/{report_id}/amend",
            )
        )

    if status not in SUBMIT_BLOCKED_STATUSES:
        actions.append(
            mutation_action(
                key="submit",
                label="הגשה לרשות המסים",
                endpoint=f"/annual-reports/{report_id}/submit",
            )
        )

    return actions
