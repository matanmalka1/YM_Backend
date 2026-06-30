from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.audit.audit_constants import (
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
    ACTION_STATUS_CHANGED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_SIGNATURE_REQUEST,
    entity_action,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.clients.models.client_record import ClientRecord
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.signature_requests.models.signature_request import SignatureRequest

_BULK_LIMIT = 500
_SIGNATURE_LIFECYCLE_ACTIONS = (
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
)
_ANNUAL_REPORT_STATUS_CHANGED = entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)


@dataclass(frozen=True)
class AnnualReportStatusAuditEvent:
    id: int
    from_status: AnnualReportStatus | None
    to_status: AnnualReportStatus
    note: str | None
    occurred_at: datetime


def _status_from_snapshot(snapshot: object) -> AnnualReportStatus | None:
    if not isinstance(snapshot, dict):
        return None
    status = snapshot.get("status")
    if status is None:
        return None
    return AnnualReportStatus(status)


class TimelineRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_client_record(self, client_record_id: int) -> ClientRecord | None:
        return self.db.scalars(
            select(ClientRecord).where(
                ClientRecord.id == client_record_id,
                ClientRecord.deleted_at.is_(None),
            )
        ).first()

    def list_permanent_documents(self, business_ids: list[int]) -> list[PermanentDocument]:
        if not business_ids:
            return []
        return list(
            self.db.scalars(
                select(PermanentDocument)
                .where(
                    PermanentDocument.business_id.in_(business_ids),
                    PermanentDocument.is_deleted.is_(False),
                )
                .limit(_BULK_LIMIT)
            ).all()
        )

    def list_signature_lifecycle_events(
        self,
        client_record_id: int,
    ) -> list[tuple[SignatureRequest, EntityAuditLog]]:
        rows = self.db.execute(
            select(SignatureRequest, EntityAuditLog)
            .join(
                EntityAuditLog,
                and_(
                    EntityAuditLog.entity_type == ENTITY_SIGNATURE_REQUEST,
                    EntityAuditLog.entity_id == SignatureRequest.id,
                ),
            )
            .where(
                SignatureRequest.client_record_id == client_record_id,
                SignatureRequest.deleted_at.is_(None),
                EntityAuditLog.action.in_(_SIGNATURE_LIFECYCLE_ACTIONS),
            )
            .order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc())
            .limit(_BULK_LIMIT)
        ).all()
        return [(sig, audit) for sig, audit in rows]

    def list_annual_report_status_events(
        self, client_record_id: int | None
    ) -> list[tuple[AnnualReport, AnnualReportStatusAuditEvent]]:
        stmt = (
            select(AnnualReport, EntityAuditLog)
            .join(
                EntityAuditLog,
                and_(
                    EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT,
                    EntityAuditLog.entity_id == AnnualReport.id,
                    EntityAuditLog.action == _ANNUAL_REPORT_STATUS_CHANGED,
                ),
            )
            .where(AnnualReport.deleted_at.is_(None))
        )
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        rows = self.db.execute(
            stmt.order_by(EntityAuditLog.performed_at.desc(), EntityAuditLog.id.desc()).limit(
                _BULK_LIMIT
            )
        ).all()
        events: list[tuple[AnnualReport, AnnualReportStatusAuditEvent]] = []
        for report, audit in rows:
            to_status = _status_from_snapshot(audit.new_value)
            if to_status is None:
                continue
            events.append(
                (
                    report,
                    AnnualReportStatusAuditEvent(
                        id=audit.id,
                        from_status=_status_from_snapshot(audit.old_value),
                        to_status=to_status,
                        note=audit.note,
                        occurred_at=audit.performed_at,
                    ),
                )
            )
        return events

    def list_annual_report_ids(self, client_record_id: int) -> list[int]:
        """All (non-deleted) annual-report ids for a client — for audit lookup."""
        return list(
            self.db.scalars(
                select(AnnualReport.id).where(
                    AnnualReport.client_record_id == client_record_id,
                    AnnualReport.deleted_at.is_(None),
                )
            ).all()
        )
