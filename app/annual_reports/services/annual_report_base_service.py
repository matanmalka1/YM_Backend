from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annual_reports.annual_report_constants import VALID_TRANSITIONS
from app.annual_reports.annual_report_messages import ANNUAL_REPORT_NOT_FOUND
from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.schemas.annual_report_responses import (
    AnnualReportListItem,
    AnnualReportResponse,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.legal_entities.models.legal_entity import LegalEntity

if TYPE_CHECKING:
    from app.clients.repositories.client_record_repository import ClientRecordRepository


class AnnualReportBaseService:
    """Shared helpers for annual report service mixins."""

    db: Session  # set by concrete service
    repo: Any  # set by concrete service
    business_repo: Any  # set by concrete service
    user_repo: Any  # set by concrete service
    client_repo: ClientRecordRepository  # set by concrete service

    def _get_or_raise(self, report_id: int) -> AnnualReport:
        report = self.repo.get_by_id(report_id)
        if not report:
            raise NotFoundError(
                ANNUAL_REPORT_NOT_FOUND.format(report_id=report_id),
                ErrorCode.ANNUAL_REPORT_NOT_FOUND,
            )
        return report

    def _resolve_client_context(self, reports: list[AnnualReport]) -> tuple[dict, dict]:
        """Resolve client records + legal entities for a batch of reports.

        Returns (records_by_id, legal_entities_by_id). Shared by both the full
        response mapper and the thin list mapper so the client-context join is
        only written once.
        """
        client_record_ids = {r.client_record_id for r in reports}
        records = (
            {record.id: record for record in self.client_repo.list_by_ids(list(client_record_ids))}
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
        return records, legal_entities

    def _to_responses(self, reports: list[AnnualReport]) -> list[AnnualReportResponse]:
        """
        Project ORM instances to AnnualReportResponse, populating client context
        and allowed transitions. Used by detail/single paths.
        Reports are now client-scoped; business_name is resolved from the client's
        primary business (first non-deleted business) for display purposes.
        """
        if not reports:
            return []
        records, legal_entities = self._resolve_client_context(reports)

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
            allowed = VALID_TRANSITIONS.get(r.status, set())
            obj.available_transitions = [
                status for status in AnnualReportStatus if status in allowed
            ]
            result.append(obj)
        return result

    def _to_list_items(self, reports: list[AnnualReport]) -> list[AnnualReportListItem]:
        """
        Project ORM instances to the thin AnnualReportListItem for list endpoints.
        Resolves client context but intentionally skips the per-row action and
        transition computation that the list UI does not render.
        """
        if not reports:
            return []
        records, legal_entities = self._resolve_client_context(reports)

        result = []
        for r in reports:
            obj = AnnualReportListItem.model_validate(r)
            record = records.get(r.client_record_id)
            legal_entity = legal_entities.get(record.legal_entity_id) if record else None
            if record and legal_entity:
                obj.office_client_number = record.office_client_number
                obj.client_name = legal_entity.official_name
                obj.client_id_number = legal_entity.id_number
            result.append(obj)
        return result
