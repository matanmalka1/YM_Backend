from app.annual_reports.models.annual_report_enums import ClientAnnualFilingType
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.models.annual_report_schedule_entry import AnnualReportSchedule
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError

from ..annual_report_constants import SCHEDULE_FLAGS
from ..annual_report_financial_line_helpers import assert_report_unlocked
from ..annual_report_messages import INVALID_SCHEDULE_ERROR, SCHEDULE_NOT_FOUND
from .annual_report_base_service import AnnualReportBaseService


class AnnualReportScheduleService(AnnualReportBaseService):
    def add_schedule(self, report_id: int, schedule: str, notes: str | None = None):
        assert_report_unlocked(self._get_or_raise(report_id))
        s = self._parse_schedule(schedule)
        return self.repo.add_schedule(report_id, s, notes=notes)

    def complete_schedule(self, report_id: int, schedule: str):
        assert_report_unlocked(self._get_or_raise(report_id))
        s = self._parse_schedule(schedule)
        entry = self.repo.mark_schedule_complete(report_id, s)
        if not entry:
            raise NotFoundError(
                SCHEDULE_NOT_FOUND.format(schedule=schedule, report_id=report_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        return entry

    def _parse_schedule(self, schedule: str) -> AnnualReportSchedule:
        try:
            return AnnualReportSchedule(schedule)
        except ValueError as exc:
            raise AppError(
                INVALID_SCHEDULE_ERROR.format(schedule=schedule),
                ErrorCode.ANNUAL_REPORT_INVALID_TYPE,
            ) from exc

    def get_schedules(self, report_id: int):
        self._get_or_raise(report_id)
        return self.repo.get_schedules(report_id)

    def schedules_complete(self, report_id: int) -> bool:
        return self.repo.schedules_complete(report_id)

    # internal
    def _generate_schedules(self, report: AnnualReport) -> None:
        if report.client_type in {
            ClientAnnualFilingType.SELF_EMPLOYED,
            ClientAnnualFilingType.PARTNERSHIP,
        }:
            self.repo.add_schedule(
                annual_report_id=report.id,
                schedule=AnnualReportSchedule.SCHEDULE_A,
                is_required=True,
            )
        if report.client_type == ClientAnnualFilingType.PARTNERSHIP:
            self.repo.add_schedule(
                annual_report_id=report.id,
                schedule=AnnualReportSchedule.FORM_1504,
                is_required=True,
            )
        for flag_attr, schedule in SCHEDULE_FLAGS:
            if getattr(report, flag_attr, False):
                self.repo.add_schedule(
                    annual_report_id=report.id,
                    schedule=schedule,
                    is_required=True,
                )
