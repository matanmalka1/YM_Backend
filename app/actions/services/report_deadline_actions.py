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


def get_annual_report_actions(status: str) -> list[ActionDescriptor]:
    """Return available actions for an annual report based on its status."""
    actions: list[ActionDescriptor] = []

    if status == AnnualReportStatus.SUBMITTED.value:
        actions.append(
            mutation_action(
                key="amend",
                label="תיקון דוח",
            )
        )

    if status not in SUBMIT_BLOCKED_STATUSES:
        actions.append(
            mutation_action(
                key="submit",
                label="הגשה לרשות המסים",
            )
        )

    return actions
