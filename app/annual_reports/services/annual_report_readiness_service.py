"""Annual report filing readiness service."""

from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_schedule_entry import (
    AnnualReportScheduleEntry,
)
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.annual_reports.repositories.annual_report_detail_repository import (
    AnnualReportDetailRepository,
)
from app.annual_reports.repositories.annual_report_income_repository import (
    AnnualReportIncomeRepository,
)
from app.annual_reports.schemas.annual_report_financials import ReadinessCheckResponse
from app.annual_reports.services.annual_report_labels import SCHEDULE_LABELS
from app.annual_reports.annual_report_messages import (
    ANNUAL_REPORT_NOT_FOUND,
    CLIENT_NOT_APPROVED_REPORT_ISSUE,
    INCOMPLETE_REQUIRED_SCHEDULE_ISSUE,
    MISSING_REPORT_INCOME_ISSUE,
    MISSING_TAX_CALCULATION_ISSUE,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class AnnualReportReadinessService:
    """Evaluate whether an annual report can be submitted."""

    _SCHEDULE_LABELS = SCHEDULE_LABELS

    def __init__(self, db: Session):
        self.report_repo = AnnualReportRepository(db)
        self.detail_repo = AnnualReportDetailRepository(db)
        self.income_repo = AnnualReportIncomeRepository(db)

    def get_readiness_check(self, report_id: int) -> ReadinessCheckResponse:
        total_checks = 4
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )

        issues: list[str] = []
        passed = 0

        schedules = self.report_repo.get_schedules(report_id)
        required = [s for s in schedules if s.is_required]
        schedule_issues = self._required_schedule_issues(required)
        if schedule_issues:
            issues.extend(schedule_issues)
        else:
            passed += 1

        total_income = self.income_repo.total_income(report_id)
        if total_income == 0:
            issues.append(MISSING_REPORT_INCOME_ISSUE)
        else:
            passed += 1

        detail = self.detail_repo.get_by_report_id(report_id)
        if report.tax_due is None and report.refund_due is None:
            issues.append(MISSING_TAX_CALCULATION_ISSUE)
        else:
            passed += 1

        if not detail or not detail.client_approved_at:
            issues.append(CLIENT_NOT_APPROVED_REPORT_ISSUE)
        else:
            passed += 1

        completion_pct = round(passed / total_checks * 100, 1)
        return ReadinessCheckResponse(
            annual_report_id=report_id,
            is_ready=len(issues) == 0,
            issues=issues,
            completion_pct=completion_pct,
        )

    def _required_schedule_issues(
        self, required_schedules: list[AnnualReportScheduleEntry]
    ) -> list[str]:
        return [
            INCOMPLETE_REQUIRED_SCHEDULE_ISSUE.format(
                label=self._schedule_label(schedule.schedule.value)
            )
            for schedule in required_schedules
            if not schedule.is_complete
        ]

    def _schedule_label(self, schedule_value: str) -> str:
        return self._SCHEDULE_LABELS.get(schedule_value, schedule_value)


__all__ = ["AnnualReportReadinessService"]
