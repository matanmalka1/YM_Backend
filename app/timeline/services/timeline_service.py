from datetime import date
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_BINDER_MARKED_FULL,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_BINDER_REOPENED,
    ACTION_BINDER_REVERTED_READY,
    ENTITY_BINDER,
)
from app.audit.repositories.audit_entity_audit_log_repository import EntityAuditLogRepository
from app.binders.repositories.binder_repository import BinderRepository
from app.businesses.repositories.business_repository import BusinessRepository
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.pagination import paginate_sequence
from app.invoices.repositories.invoice_repository import InvoiceRepository
from app.notifications.models.notification import NotificationStatus
from app.notifications.repositories.notification_repository import NotificationRepository
from app.timeline.repositories.timeline_repository import TimelineRepository
from app.timeline.timeline_audit_aggregator import build_entity_audit_events
from app.timeline.timeline_binder_event_builders import (
    binder_handed_over_event,
    binder_lifecycle_change_event,
    binder_received_event,
)
from app.timeline.timeline_charge_event_builders import (
    charge_created_event,
    charge_issued_event,
    charge_paid_event,
    invoice_attached_event,
)
from app.timeline.timeline_client_aggregator import build_client_events
from app.timeline.timeline_notification_event_builders import (
    notification_failed_event,
    notification_sent_event,
)
from app.timeline.timeline_tax_builders import (
    annual_report_status_changed_event,
)

# Safety ceiling for per-entity bulk fetches — per-client, not global.
_TIMELINE_BULK_LIMIT = 500

# Fixed page size — timeline has no user-facing page-size control.
DEFAULT_TIMELINE_PAGE_SIZE = 20


class TimelineService:
    """Unified client timeline aggregation."""

    def __init__(self, db: Session):
        self.db = db
        self.binder_repo = BinderRepository(db)
        self.entity_audit_repo = EntityAuditLogRepository(db)
        self.business_repo = BusinessRepository(db)
        self.charge_repo = ChargeRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.client_record_repo = ClientRecordRepository(db)
        self.notification_repo = NotificationRepository(db)
        self.timeline_repo = TimelineRepository(db)

    def get_client_timeline(
        self,
        client_record_id: int,
        page: int = 1,
        page_size: int = DEFAULT_TIMELINE_PAGE_SIZE,
        search: str | None = None,
        event_types: list[str] | None = None,
        important_only: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[dict], int]:
        client_record = self.client_record_repo.get_by_id(client_record_id)
        if not client_record:
            raise NotFoundError(message="לקוח לא נמצא", code=ErrorCode.TIMELINE_CLIENT_NOT_FOUND)
        businesses = self.business_repo.list_by_legal_entity_ids([client_record.legal_entity_id])
        business_ids = [business.id for business in businesses]
        client_record_id = int(client_record.id)

        events = []

        # Bounded: _TIMELINE_BULK_LIMIT — older binders silently excluded if exceeded.
        binders = self.binder_repo.list_by_client_record(client_record_id)
        for binder in binders:
            if getattr(binder, "received_at", None) or getattr(binder, "period_start", None):
                events.append(binder_received_event(binder))
            if binder.handed_over_at:
                events.append(binder_handed_over_event(binder))
            self._append_lifecycle_change_events(events, binder)

        # Bounded fetch — clients with more than _TIMELINE_BULK_LIMIT
        # charges will have older events silently truncated.
        charges = self.charge_repo.list_charges(
            business_ids=business_ids, page=1, page_size=_TIMELINE_BULK_LIMIT
        )
        invoice_map = {
            inv.charge_id: inv
            for inv in self.invoice_repo.list_by_charge_ids([c.id for c in charges])
        }
        for charge in charges:
            events.append(charge_created_event(charge))
            if charge.issued_at:
                events.append(charge_issued_event(charge))
            if charge.paid_at:
                events.append(charge_paid_event(charge))
            invoice = invoice_map.get(charge.id)
            if invoice:
                events.append(invoice_attached_event(charge, invoice))

        events.extend(self._build_annual_report_events(client_record.id if client_record else None))
        events.extend(build_client_events(self.db, client_record_id, business_ids))
        events.extend(self._build_notification_events(client_record_id))
        events.extend(
            build_entity_audit_events(
                self.db,
                client_record_id=client_record_id,
                business_ids=business_ids,
                charge_ids=[charge.id for charge in charges],
                report_ids=self.timeline_repo.list_annual_report_ids(client_record_id),
            )
        )

        events = self._filter_by_date_range(events, date_from, date_to)
        events.sort(key=lambda e: e["timestamp"], reverse=True)

        if search:
            q = search.strip().lower()
            events = [
                e
                for e in events
                if q in (e.get("description") or "").lower()
                or q in str(e.get("binder_id") or "")
                or q in str(e.get("charge_id") or "")
                or any(q in str(v).lower() for v in (e.get("metadata") or {}).values())
            ]
        if event_types:
            events = [e for e in events if e.get("event_type") in event_types]
        if important_only:
            _STRONG = {
                "charge_created",
                "charge_issued",
                "charge_paid",
                "annual_report_status_changed",
                "binder_lifecycle_change",
                "document_uploaded",
                "signature_request_sent",
                "signature_request_signed",
                "signature_request_declined",
            }
            events = [e for e in events if e.get("event_type") in _STRONG]

        total = len(events)
        return paginate_sequence(events, page, page_size), total

    @staticmethod
    def _filter_by_date_range(
        events: list[dict], date_from: date | None, date_to: date | None
    ) -> list[dict]:
        """Keep events whose timestamp date falls within [date_from, date_to]."""
        if date_from is None and date_to is None:
            return events

        def in_range(event: dict) -> bool:
            timestamp = event["timestamp"]
            event_date = timestamp.date() if hasattr(timestamp, "date") else timestamp
            if date_from is not None and event_date < date_from:
                return False
            if date_to is not None and event_date > date_to:
                return False
            return True

        return [event for event in events if in_range(event)]

    # Binder lifecycle transitions surfaced in the timeline. binder.created /
    # binder.material_received are covered by the live binder_received builder and
    # binder.handed_over by the live binder_handed_over builder, so they are excluded
    # here to keep one source per category (plan §4).
    _BINDER_LIFECYCLE_TIMELINE_ACTIONS = frozenset(
        {
            ACTION_BINDER_MARKED_FULL,
            ACTION_BINDER_REOPENED,
            ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
            ACTION_BINDER_REVERTED_READY,
        }
    )

    def _append_lifecycle_change_events(self, events: list[dict], binder) -> None:
        rows = self.entity_audit_repo.list_by_entity(ENTITY_BINDER, binder.id)
        for row in rows:
            if row.action not in self._BINDER_LIFECYCLE_TIMELINE_ACTIONS:
                continue
            events.append(binder_lifecycle_change_event(binder, self._lifecycle_log_view(row)))

    @staticmethod
    def _lifecycle_log_view(row):
        """Adapt an EntityAuditLog binder row to the lifecycle-log shape the timeline
        binder event builder reads (field_name/old_value/new_value/notes/changed_at)."""
        old_value = row.old_value or {}
        new_value = row.new_value or {}
        field_name = next(iter(new_value), next(iter(old_value), ""))
        return SimpleNamespace(
            field_name=field_name,
            old_value=old_value.get(field_name),
            new_value=new_value.get(field_name),
            notes=row.note,
            changed_at=row.performed_at,
        )

    def _build_notification_events(self, client_record_id: int) -> list[dict]:
        notifications, _ = self.notification_repo.list_paginated(
            client_record_id=client_record_id,
            statuses=[NotificationStatus.SENT, NotificationStatus.FAILED],
            page=1,
            page_size=_TIMELINE_BULK_LIMIT,
        )
        events = []
        for n in notifications:
            if n.status == NotificationStatus.SENT:
                events.append(notification_sent_event(n))
            else:
                events.append(notification_failed_event(n))
        return events

    def _build_annual_report_events(self, client_record_id: int | None) -> list[dict]:
        rows = self.timeline_repo.list_annual_report_status_events(client_record_id)
        return [annual_report_status_changed_event(report, history) for report, history in rows]
