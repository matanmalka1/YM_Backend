from datetime import date, datetime
from enum import Enum

from sqlalchemy.orm import Session

from app.annual_reports.annual_report_messages import ANNUAL_REPORT_NOT_FOUND
from app.annual_reports.models.annual_report_detail import AnnualReportDetail
from app.annual_reports.repositories.annual_report_detail_repository import (
    AnnualReportDetailRepository,
)
from app.annual_reports.repositories.annual_report_repository import (
    AnnualReportRepository,
)
from app.audit.audit_constants import (
    ACTION_ANNUAL_REPORT_DETAIL_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError


class AnnualReportDetailService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AnnualReportDetailRepository(db)
        self.report_repo = AnnualReportRepository(db)

    def get_detail(self, report_id: int) -> AnnualReportDetail | None:
        return self.repo.get_by_report_id(report_id)

    def update_detail(
        self, report_id: int, actor_id: int | None = None, actor_name: str | None = None, **fields
    ) -> AnnualReportDetail:
        report = self.report_repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        existing = self.repo.get_by_report_id(report_id)
        changes = {
            key: value
            for key, value in fields.items()
            if _audit_value(getattr(existing, key, None)) != _audit_value(value)
        }
        old_value = {key: getattr(existing, key, None) for key in changes} if changes else None
        detail = self.repo.update_meta(report_id, **fields)
        if changes:
            EntityAuditWriter(self.db).append(
                entity_type=ENTITY_ANNUAL_REPORT,
                entity_id=report_id,
                actor_id=actor_id,
                action=ACTION_ANNUAL_REPORT_DETAIL_UPDATED,
                old_value=old_value,
                new_value=changes,
                actor_display_name=actor_name,
                metadata_json={
                    "client_record_id": report.client_record_id,
                    "tax_year": report.tax_year,
                },
            )
        return detail


def _audit_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
