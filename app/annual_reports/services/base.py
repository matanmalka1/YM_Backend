from typing import Any

from sqlalchemy import select

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.schemas.annual_report_responses import AnnualReportResponse
from app.annual_reports.services.constants import VALID_TRANSITIONS
from app.annual_reports.services.messages import ANNUAL_REPORT_NOT_FOUND
from app.clients.models.legal_entity import LegalEntity
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import NotFoundError


class AnnualReportBaseService:
    """Shared helpers for annual report service mixins."""

    repo: Any  # set by concrete service
    business_repo: Any  # set by concrete service
    user_repo: Any  # set by concrete service

    def _get_or_raise(self, report_id: int) -> AnnualReport:
        report = self.repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                "ANNUAL_REPORT.NOT_FOUND",
            )
        return report

    def _to_responses(self, reports: list[AnnualReport]) -> list[AnnualReportResponse]:
        """
        Project ORM instances to AnnualReportResponse, populating client context.
        Reports are now client-scoped; business_name is resolved from the client's
        primary business (first non-deleted business) for display purposes.
        """
        if not reports:
            return []
        client_record_ids = {r.client_record_id for r in reports}
        records = (
            {
                record.id: record
                for record in ClientRecordRepository(self.db).list_by_ids(list(client_record_ids))
            }
            if client_record_ids
            else {}
        )
        legal_entity_ids = {record.legal_entity_id for record in records.values()}
        legal_entities = (
            {
                entity.id: entity
                for entity in self.db.scalars(
                    select(LegalEntity).where(LegalEntity.id.in_(legal_entity_ids))
                ).all()
            }
            if legal_entity_ids
            else {}
        )

        from app.actions.services.report_deadline_actions import get_annual_report_actions

        result = []
        for r in reports:
            obj = AnnualReportResponse.model_validate(r)
            record = records.get(r.client_record_id)
            legal_entity = legal_entities.get(record.legal_entity_id) if record else None
            if record and legal_entity:
                obj.office_client_number = record.office_client_number
                obj.client_name = legal_entity.official_name
                obj.client_id_number = legal_entity.id_number
                obj.business_name = legal_entity.official_name
            obj.available_actions = get_annual_report_actions(
                r.id, r.status.value if hasattr(r.status, "value") else str(r.status)
            )
            allowed = VALID_TRANSITIONS.get(r.status, set())
            obj.available_transitions = [
                status for status in AnnualReportStatus if status in allowed
            ]
            result.append(obj)
        return result
