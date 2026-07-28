from app.annual_reports.models.annual_report_enums import (
    AnnualReportSchedule,
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
    "STUCK_REPORT_STALE_DAYS",
    "STUCK_REPORT_LIMIT",
]
