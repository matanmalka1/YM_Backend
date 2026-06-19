from app.annual_reports.models.annual_report_enums import (
    AnnualReportSchedule,
    AnnualReportStatus,
    ClientAnnualFilingType,
    PrimaryAnnualReportForm,
)

# Which main annual-return form each filing profile uses inside this domain.
#
# Important: this domain manages full annual returns. Form 0135 remains a
# supported ITA form value for reference, but it is not the primary workflow
# here because it is a short refund request for taxpayers who are not required
# to file a full annual return.
FORM_MAP: dict[ClientAnnualFilingType, PrimaryAnnualReportForm] = {
    ClientAnnualFilingType.INDIVIDUAL: PrimaryAnnualReportForm.FORM_1301,
    ClientAnnualFilingType.SELF_EMPLOYED: PrimaryAnnualReportForm.FORM_1301,
    ClientAnnualFilingType.PARTNERSHIP: PrimaryAnnualReportForm.FORM_1301,
    ClientAnnualFilingType.CONTROL_HOLDER: PrimaryAnnualReportForm.FORM_1301,
    ClientAnnualFilingType.CORPORATION: PrimaryAnnualReportForm.FORM_1214,
    ClientAnnualFilingType.PUBLIC_INSTITUTION: PrimaryAnnualReportForm.FORM_1215,
    ClientAnnualFilingType.EXEMPT_DEALER: PrimaryAnnualReportForm.FORM_1301,
}

# Valid status transitions (from → set of allowed next statuses)
VALID_TRANSITIONS: dict[AnnualReportStatus, set[AnnualReportStatus]] = {
    AnnualReportStatus.NOT_STARTED: {AnnualReportStatus.COLLECTING_DOCS},
    AnnualReportStatus.COLLECTING_DOCS: {
        AnnualReportStatus.IN_PREPARATION,
        AnnualReportStatus.NOT_STARTED,
    },
    AnnualReportStatus.IN_PREPARATION: {
        AnnualReportStatus.PENDING_CLIENT,
        AnnualReportStatus.COLLECTING_DOCS,
    },
    AnnualReportStatus.PENDING_CLIENT: {
        AnnualReportStatus.IN_PREPARATION,
        AnnualReportStatus.SUBMITTED,
    },
    AnnualReportStatus.SUBMITTED: {
        AnnualReportStatus.IN_PREPARATION,
        AnnualReportStatus.CLOSED,
    },
    AnnualReportStatus.CLOSED: set(),
    AnnualReportStatus.CANCELED: set(),
}

# ── Stage shortcut → status mapping (one-way: promotes to first status in stage) ──
# Note: this map intentionally moves to a single target status per stage.
# Demoting within a stage requires direct status transition.
STAGE_TO_STATUS: dict[str, str] = {
    "material_collection": "collecting_docs",
    "in_progress": "in_preparation",
    "final_review": "in_preparation",
    "client_signature": "pending_client",
    "transmitted": "submitted",
}

# ── Stuck-report defaults ──────────────────────────────────────────────────────
STUCK_REPORT_STALE_DAYS = 7
STUCK_REPORT_LIMIT = 3
ANNUAL_DEADLINE_REMINDER_DAYS_BEFORE = 7

# Which schedules are triggered by income flags
SCHEDULE_FLAGS = [
    ("has_rental_income", AnnualReportSchedule.SCHEDULE_B),
    ("has_capital_gains", AnnualReportSchedule.SCHEDULE_GIMMEL),
    ("has_foreign_income", AnnualReportSchedule.SCHEDULE_DALET),
]

__all__ = [
    "FORM_MAP",
    "ANNUAL_DEADLINE_REMINDER_DAYS_BEFORE",
    "SCHEDULE_FLAGS",
    "STAGE_TO_STATUS",
    "STUCK_REPORT_STALE_DAYS",
    "STUCK_REPORT_LIMIT",
    "VALID_TRANSITIONS",
]
