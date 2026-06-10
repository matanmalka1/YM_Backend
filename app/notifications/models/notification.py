"""
Notification — outbound message sent to a client contact.

Design:
- client_record_id is the primary anchor (legal entity record).
- recipient is nullable: skipped notifications (no email) save recipient=null.
- content_snapshot + subject_snapshot store rendered text at send time — immutable audit.
- entity_type/entity_id are generic domain anchors (charge, vat_work_item, etc.).
- Named FKs binder_id/annual_report_id/signature_request_id kept for repo query convenience.
- triggered_by=null means system-triggered; user_id means manual.
- No updated_at — status transitions captured via sent_at/failed_at.
"""

from __future__ import annotations

import datetime
from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class NotificationChannel(str, PyEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class NotificationStatus(str, PyEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationTrigger(str, PyEnum):
    BINDER_READY_FOR_HANDOVER = "binder_ready_for_handover"
    BINDER_MISSING_DOCUMENTS = "binder_missing_documents"
    BINDER_GENERAL_REMINDER = "binder_general_reminder"
    INVOICE_ISSUED = "invoice_issued"
    PAYMENT_REMINDER = "payment_reminder"
    VAT_DOCUMENTS_REMINDER = "vat_documents_reminder"
    ANNUAL_REPORT_DOCUMENTS_REQUEST = "annual_report_documents_request"
    ANNUAL_REPORT_CLIENT_REMINDER = "annual_report_client_reminder"
    SIGNATURE_REQUEST_SENT = "signature_request_sent"
    SIGNATURE_REQUEST_REMINDER = "signature_request_reminder"
    CLIENT_MISSING_INFORMATION = "client_missing_information"
    CLIENT_DOCUMENTS_REQUEST = "client_documents_request"
    CLIENT_GENERAL_MESSAGE = "client_general_message"


TRIGGER_LABELS: dict[NotificationTrigger, str] = {
    NotificationTrigger.BINDER_READY_FOR_HANDOVER: "קלסר מוכן למסירה",
    NotificationTrigger.BINDER_MISSING_DOCUMENTS: "מסמכים חסרים בקלסר",
    NotificationTrigger.BINDER_GENERAL_REMINDER: "תזכורת כללית - קלסר",
    NotificationTrigger.INVOICE_ISSUED: "חשבונית הונפקה",
    NotificationTrigger.PAYMENT_REMINDER: "תזכורת לתשלום",
    NotificationTrigger.VAT_DOCUMENTS_REMINDER: "תזכורת מסמכי מע״מ",
    NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST: "בקשת מסמכים לדוח שנתי",
    NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER: "תזכורת אישור דוח שנתי",
    NotificationTrigger.SIGNATURE_REQUEST_SENT: "בקשה לחתימה",
    NotificationTrigger.SIGNATURE_REQUEST_REMINDER: "תזכורת לחתימה",
    NotificationTrigger.CLIENT_MISSING_INFORMATION: "פרטים חסרים",
    NotificationTrigger.CLIENT_DOCUMENTS_REQUEST: "בקשת מסמכים",
    NotificationTrigger.CLIENT_GENERAL_MESSAGE: "הודעה כללית",
}

TRIGGER_DOMAIN: dict[NotificationTrigger, str] = {
    NotificationTrigger.BINDER_READY_FOR_HANDOVER: "binders",
    NotificationTrigger.BINDER_MISSING_DOCUMENTS: "binders",
    NotificationTrigger.BINDER_GENERAL_REMINDER: "binders",
    NotificationTrigger.INVOICE_ISSUED: "charges",
    NotificationTrigger.PAYMENT_REMINDER: "charges",
    NotificationTrigger.VAT_DOCUMENTS_REMINDER: "vat",
    NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST: "annual_reports",
    NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER: "annual_reports",
    NotificationTrigger.SIGNATURE_REQUEST_SENT: "signatures",
    NotificationTrigger.SIGNATURE_REQUEST_REMINDER: "signatures",
    NotificationTrigger.CLIENT_MISSING_INFORMATION: "clients",
    NotificationTrigger.CLIENT_DOCUMENTS_REQUEST: "clients",
    NotificationTrigger.CLIENT_GENERAL_MESSAGE: "clients",
}


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Anchors ───────────────────────────────────────────────────────────────
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    binder_id: Mapped[int | None] = mapped_column(
        ForeignKey("binders.id"), nullable=True, index=True
    )
    annual_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("annual_reports.id"), nullable=True, index=True
    )
    signature_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("signature_requests.id"), nullable=True, index=True
    )
    # Generic domain anchor (charge_id, vat_work_item_id, etc.)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)

    # ── Message identity ──────────────────────────────────────────────────────
    trigger: Mapped[NotificationTrigger] = mapped_column(
        pg_enum(NotificationTrigger), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        pg_enum(NotificationChannel), nullable=False
    )
    # nullable: skipped records have no recipient
    recipient: Mapped[str | None] = mapped_column(String, nullable=True)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    subject_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Delivery status ───────────────────────────────────────────────────────
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus),
        default=NotificationStatus.PENDING,
        nullable=False,
    )
    sent_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    failed_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # ── Idempotency ───────────────────────────────────────────────────────────
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_notification_status", "status"),
        Index("idx_notification_client_record_status", "client_record_id", "status"),
        Index("idx_notification_business_status", "business_id", "status"),
        Index("idx_notification_created_at", "created_at"),
        Index("idx_notification_trigger", "trigger"),
        Index("idx_notification_triggered_by", "triggered_by"),
        Index("idx_notification_idempotency", "idempotency_key"),
        Index("idx_notification_signature_request", "signature_request_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, client_record_id={self.client_record_id}, "
            f"trigger='{self.trigger}', status='{self.status}')>"
        )
