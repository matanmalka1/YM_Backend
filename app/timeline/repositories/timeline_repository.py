from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.models.annual_report_status_history import AnnualReportStatusHistory
from app.clients.models.client_record import ClientRecord
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.signature_requests.models.signature_request import (
    SignatureAuditEvent,
    SignatureRequest,
)

_BULK_LIMIT = 500
_SIGNATURE_LIFECYCLE_TYPES = ("sent", "signed", "declined", "canceled", "expired")


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
    ) -> list[tuple[SignatureRequest, SignatureAuditEvent]]:
        rows = self.db.execute(
            select(SignatureRequest, SignatureAuditEvent)
            .join(
                SignatureAuditEvent,
                SignatureAuditEvent.signature_request_id == SignatureRequest.id,
            )
            .where(
                SignatureRequest.client_record_id == client_record_id,
                SignatureRequest.deleted_at.is_(None),
                SignatureAuditEvent.event_type.in_(_SIGNATURE_LIFECYCLE_TYPES),
            )
            .order_by(SignatureAuditEvent.occurred_at.desc())
            .limit(_BULK_LIMIT)
        ).all()
        return [(sig, audit) for sig, audit in rows]

    def list_annual_report_status_events(
        self, client_record_id: int | None
    ) -> list[tuple[AnnualReport, AnnualReportStatusHistory]]:
        stmt = (
            select(AnnualReport, AnnualReportStatusHistory)
            .join(
                AnnualReportStatusHistory,
                AnnualReportStatusHistory.annual_report_id == AnnualReport.id,
            )
            .where(AnnualReport.deleted_at.is_(None))
        )
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        rows = self.db.execute(
            stmt.order_by(AnnualReportStatusHistory.occurred_at.desc()).limit(_BULK_LIMIT)
        ).all()
        return [(report, history) for report, history in rows]
