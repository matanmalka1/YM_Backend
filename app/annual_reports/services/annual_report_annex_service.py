"""Service mixin for annex (schedule) data lines."""

from app.annual_reports.models.annual_report_annex_data import AnnualReportAnnexData
from app.annual_reports.models.annual_report_enums import AnnualReportSchedule
from app.annual_reports.schemas.annual_report_annex_schemas import SCHEDULE_VALIDATORS
from app.annual_reports.schemas.annual_report_annex import AnnexDataLineResponse
from app.audit.audit_constants import (
    ACTION_ANNEX_LINE_ADDED,
    ACTION_ANNEX_LINE_DELETED,
    ACTION_ANNEX_LINE_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.services.audit_entity_audit_writer import EntityAuditWriter
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError

from .annual_report_base import AnnualReportBaseService
from .annual_report_messages import ANNEX_LINE_NOT_FOUND, ANNEX_VALIDATION_ERROR


class AnnualReportAnnexService(AnnualReportBaseService):
    """Mixin — requires self.annex_repo (AnnexDataRepository) wired in facade __init__."""

    def _validate_annex_data(self, schedule: AnnualReportSchedule, data: dict) -> dict:
        """Validate annex data dict against the per-schedule Pydantic schema.

        Returns the validated (and coerced) data dict.
        If no schema is defined for the schedule the dict passes through unchanged.
        """
        validator_cls = SCHEDULE_VALIDATORS.get(schedule.value)
        if validator_cls is None:
            return data
        try:
            validated = validator_cls(**data)
            # Convert Decimal values to float so the dict is JSON-serializable
            # before being stored in the JSON column (SQLite/PostgreSQL JSON type).
            raw = validated.model_dump(exclude_none=True)
            return {
                k: float(v)
                if hasattr(v, "__round__") and not isinstance(v, (int, float, bool))
                else v
                for k, v in raw.items()
            }
        except Exception as exc:
            raise AppError(
                ANNEX_VALIDATION_ERROR.format(error=exc),
                ErrorCode.ANNUAL_REPORT_ANNEX_VALIDATION_ERROR,
            ) from exc

    def get_annex_lines(
        self, report_id: int, schedule: AnnualReportSchedule
    ) -> list[AnnexDataLineResponse]:
        self._get_or_raise(report_id)
        rows = self.annex_repo.list_by_report_and_schedule(report_id, schedule)  # type: ignore[attr-defined]
        return [AnnexDataLineResponse.model_validate(r) for r in rows]

    def add_annex_line(
        self,
        report_id: int,
        schedule: AnnualReportSchedule,
        data: dict,
        notes: str | None = None,
        actor_id: int | None = None,
    ) -> AnnexDataLineResponse:
        self._get_or_raise(report_id)
        data = self._validate_annex_data(schedule, data)
        schedule_entry = self.annex_repo.get_or_create_schedule_entry(report_id, schedule)  # type: ignore[attr-defined]
        line_number = self.annex_repo.next_line_number(schedule_entry.id)  # type: ignore[attr-defined]
        row = self.annex_repo.add_line(schedule_entry.id, line_number, data, notes)  # type: ignore[attr-defined]
        self._record_annex_audit(
            report_id, actor_id, ACTION_ANNEX_LINE_ADDED, new_value=_annex_snapshot(row)
        )
        return AnnexDataLineResponse.model_validate(row)

    def update_annex_line(
        self,
        report_id: int,
        line_id: int,
        data: dict,
        notes: str | None = None,
        actor_id: int | None = None,
    ) -> AnnexDataLineResponse:
        self._get_or_raise(report_id)
        existing = self.annex_repo.get_by_id(line_id)  # type: ignore[attr-defined]
        if not existing or existing.annual_report_id != report_id:
            raise NotFoundError(
                ANNEX_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        old_value = _annex_snapshot(existing)
        data = self._validate_annex_data(existing.schedule, data)
        row = self.annex_repo.update_line(line_id, data, notes)  # type: ignore[attr-defined]
        if not row:
            raise NotFoundError(
                ANNEX_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        self._record_annex_audit(
            report_id,
            actor_id,
            ACTION_ANNEX_LINE_UPDATED,
            old_value=old_value,
            new_value=_annex_snapshot(row),
        )
        return AnnexDataLineResponse.model_validate(row)

    def delete_annex_line(self, report_id: int, line_id: int, actor_id: int | None = None) -> None:
        self._get_or_raise(report_id)
        existing = self.annex_repo.get_by_id(line_id)  # type: ignore[attr-defined]
        if not existing or existing.annual_report_id != report_id:
            raise NotFoundError(
                ANNEX_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        old_value = _annex_snapshot(existing)
        if not self.annex_repo.delete_line(line_id):  # type: ignore[attr-defined]
            raise NotFoundError(
                ANNEX_LINE_NOT_FOUND.format(line_id=line_id),
                ErrorCode.ANNUAL_REPORT_LINE_NOT_FOUND,
            )
        self._record_annex_audit(
            report_id, actor_id, ACTION_ANNEX_LINE_DELETED, old_value=old_value
        )

    def _record_annex_audit(
        self, report_id: int, actor_id: int | None, action: str, **values
    ) -> None:
        EntityAuditWriter(self.db).append(
            entity_type=ENTITY_ANNUAL_REPORT,
            entity_id=report_id,
            actor_id=actor_id,
            action=action,
            **values,
        )


def _annex_snapshot(row: AnnualReportAnnexData) -> dict:
    return {
        "schedule": row.schedule.value,
        "line_id": row.id,
        "line_number": row.line_number,
        "data": row.data,
        "notes": row.notes,
    }


__all__ = ["AnnualReportAnnexService"]
