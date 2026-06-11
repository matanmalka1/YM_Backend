from __future__ import annotations

"""
Permanent Document — a file stored permanently for a client or business.

Israeli context:
  Tax advisors store identity documents (ת.ז., ייפוי כוח), engagement
  agreements, tax forms, bank approvals, and withholding certificates.
  Documents are versioned — uploading a new version supersedes the previous.

Design decisions:
- scope=CLIENT: belongs to the person (id_copy, power_of_attorney,
  engagement_agreement) — client_record_id required, business_id must be NULL.
- scope=BUSINESS: belongs to a specific business — both client_record_id and
  business_id required. client_record_id is denormalized for fast queries without JOIN.
- CheckConstraint enforces the scope/business_id invariant at DB level.
- is_deleted (soft delete) on the row; storage file is NOT deleted —
  service layer handles storage cleanup separately.
- superseded_by self-FK chains versions; only the latest has superseded_by=NULL.
- rejected_by mirrors approved_by for symmetry and audit completeness.
- annual_report_id links supporting documents to a specific report.
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import CheckConstraint

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class PermanentDocumentType(str, PyEnum):
    ID_COPY = "id_copy"  # צילום ת.ז.
    POWER_OF_ATTORNEY = "power_of_attorney"  # ייפוי כוח
    ENGAGEMENT_AGREEMENT = "engagement_agreement"  # הסכם התקשרות
    TAX_FORM = "tax_form"  # טופס מס
    RECEIPT = "receipt"  # קבלה
    INVOICE_DOC = "invoice_doc"  # חשבונית
    BANK_APPROVAL = "bank_approval"  # אישור בנקאי
    WITHHOLDING_CERTIFICATE = "withholding_certificate"  # אישור ניכוי מס במקור
    NII_APPROVAL = "nii_approval"  # אישור ביטוח לאומי
    OTHER = "other"


class DocumentStatus(str, PyEnum):
    PENDING = "pending"  # הועלה, ממתין לבדיקה
    RECEIVED = "received"  # התקבל פיזית
    APPROVED = "approved"  # אושר
    REJECTED = "rejected"  # נדחה — יש להעלות מחדש


class DocumentScope(str, PyEnum):
    CLIENT = "client"  # מסמך זהות — שייך לאדם
    BUSINESS = "business"  # מסמך עסקי — שייך לעסק


# מסמכים שמשויכים תמיד לאדם (לא לעסק ספציפי)
CLIENT_SCOPE_TYPES = {
    PermanentDocumentType.ID_COPY,
    PermanentDocumentType.POWER_OF_ATTORNEY,
    PermanentDocumentType.ENGAGEMENT_AGREEMENT,
}


class PermanentDocument(Base):
    __tablename__ = "permanent_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Ownership ─────────────────────────────────────────────────────────────
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    scope: Mapped[DocumentScope] = mapped_column(pg_enum(DocumentScope), nullable=False)

    # ── Document identity ─────────────────────────────────────────────────────
    document_type: Mapped[PermanentDocumentType] = mapped_column(
        pg_enum(PermanentDocumentType, name="documenttype"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String, nullable=False)  # מפתח ב-S3/R2
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, index=True)

    # ── Status ────────────────────────────────────────────────────────────────
    is_present: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False
    )

    # ── Versioning ────────────────────────────────────────────────────────────
    version: Mapped[int] = mapped_column(default=1, nullable=False, server_default="1")
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("permanent_documents.id"), nullable=True
    )
    superseded_by_doc: Mapped[PermanentDocument | None] = relationship(
        "PermanentDocument",
        foreign_keys="[PermanentDocument.superseded_by]",
        remote_side="PermanentDocument.id",
        uselist=False,
    )

    # ── Cross-domain link ─────────────────────────────────────────────────────
    annual_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("annual_reports.id"), nullable=True
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # מי דחה
    rejected_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(scope = 'client') OR (scope = 'business' AND business_id IS NOT NULL)",
            name="ck_document_business_scope_requires_business_id",
        ),
        Index(
            "ix_permanent_documents_client_record_type_year",
            "client_record_id",
            "document_type",
            "tax_year",
        ),
        Index(
            "ix_permanent_documents_business",
            "business_id",
            "document_type",
            "tax_year",
        ),
    )

    def __repr__(self):
        return (
            f"<PermanentDocument(id={self.id}, client_record_id={self.client_record_id}, "
            f"business_id={self.business_id}, scope='{self.scope}', "
            f"type='{self.document_type}', status='{self.status}')>"
        )
