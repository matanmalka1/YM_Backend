"""
Digital Signature Request — tracks the full lifecycle of a signature request.

  PENDING_SIGNATURE → SIGNED | DECLINED | EXPIRED | CANCELED

Israeli legal context:
  The Electronic Signature Law (5761-2001) recognises digital signatures
  as legally binding when coupled with an audit trail that proves:
    - Who was asked to sign (identity)
    - When they were asked (timestamp)
    - What they approved (content hash)
    - How they confirmed (action timestamp + IP)

Design decisions:
- client_record_id is the primary anchor (legal entity record).
- business_id is OPTIONAL context — set when the signature is scoped
  to a specific business activity.
- signing_token is a one-time URL-safe token; cleared (NULL) after
  signing / declining / canceling / expiring.
- content_hash (SHA-256) enables tamper detection of the signed content.
- signed_document_key stores the countersigned PDF in S3/R2.
- canceled_by: who canceled (advisor/system) — separate from deleted_by.
- Signature lifecycle evidence is stored in EntityAuditLog.
"""

from __future__ import annotations

import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.annual_reports.models.annual_report_model import AnnualReport
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class SignatureRequestStatus(str, PyEnum):
    PENDING_SIGNATURE = "pending_signature"
    SIGNED = "signed"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELED = "canceled"


class SignatureRequestType(str, PyEnum):
    ENGAGEMENT_AGREEMENT = "engagement_agreement"  # הסכם התקשרות
    ANNUAL_REPORT_APPROVAL = "annual_report_approval"  # אישור דוח שנתי
    POWER_OF_ATTORNEY = "power_of_attorney"  # ייפוי כוח
    VAT_RETURN_APPROVAL = "vat_return_approval"  # אישור דוח מע"מ
    CUSTOM = "custom"  # חתימה כללית


class SignatureRequest(Base):
    __tablename__ = "signature_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Anchors ───────────────────────────────────────────────────────────────
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    # OPTIONAL: set when the request is scoped to a specific business activity
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # ── Cross-domain links ────────────────────────────────────────────────────
    annual_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("annual_reports.id"), nullable=True, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("permanent_documents.id"), nullable=True
    )

    # ── Request identity ──────────────────────────────────────────────────────
    request_type: Mapped[SignatureRequestType] = mapped_column(
        pg_enum(SignatureRequestType), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # SHA-256
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)  # S3/R2 original

    # ── Signer identity ───────────────────────────────────────────────────────
    signer_name: Mapped[str] = mapped_column(String, nullable=False)
    signer_email: Mapped[str | None] = mapped_column(String, nullable=True)
    signer_phone: Mapped[str | None] = mapped_column(String, nullable=True)

    # ── Status & token ────────────────────────────────────────────────────────
    status: Mapped[SignatureRequestStatus] = mapped_column(
        pg_enum(SignatureRequestStatus),
        default=SignatureRequestStatus.PENDING_SIGNATURE,
        nullable=False,
    )
    # Unique one-time token; cleared after terminal state
    signing_token: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    # ── Lifecycle timestamps ──────────────────────────────────────────────────
    created_at: Mapped[datetime.datetime] = mapped_column(default=utcnow, nullable=False)
    # Set only on real mutation of the request row (send/sign/decline/cancel/expire/
    # soft-delete). NULL until first update — never faked from created_at. The
    # Generic EntityAuditLog rows are the detailed audit source of truth.
    # updated_at stays a row-mutation timestamp, not an audit timestamp.
    updated_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True, onupdate=utcnow)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    expiry_days: Mapped[int] = mapped_column(nullable=False, default=14, server_default="14")
    signed_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    declined_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    canceled_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    canceled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # ── Signer evidence (captured at signing/declining time) ──────────────────
    signer_ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
    signer_user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_document_key: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # S3/R2 countersigned PDF

    # ── Soft delete ───────────────────────────────────────────────────────────
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    annual_report: Mapped[AnnualReport | None] = relationship(
        "AnnualReport",
        foreign_keys="[SignatureRequest.annual_report_id]",
        viewonly=True,
    )
    __table_args__ = (
        Index("idx_sig_request_client_record", "client_record_id"),
        Index("idx_sig_request_business", "business_id"),
        Index("idx_sig_request_annual_report", "annual_report_id"),
        Index("idx_sig_request_status", "status"),
        Index(
            "idx_sig_request_pending_sent_active",
            "status",
            "sent_at",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SignatureRequest(id={self.id}, client_record_id={self.client_record_id}, "
            f"business_id={self.business_id}, type='{self.request_type}', "
            f"status='{self.status}')>"
        )
