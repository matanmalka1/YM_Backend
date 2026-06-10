from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class ChargeType(str, PyEnum):
    MONTHLY_RETAINER = "monthly_retainer"  # Monthly retainer
    ANNUAL_REPORT_FEE = "annual_report_fee"  # For a specific annual report
    VAT_FILING_FEE = "vat_filing_fee"  # VAT work outside the retainer
    REPRESENTATION_FEE = "representation_fee"  # Representation in discussions / objections
    CONSULTATION_FEE = "consultation_fee"  # One-time consultation
    OTHER = "other"


class ChargeStatus(str, PyEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    CANCELED = "canceled"


class Charge(Base):
    __tablename__ = "charges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Anchors ───────────────────────────────────────────────────────────────
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    # OPTIONAL: set only when the charge is specific to one business
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    # OPTIONAL: link to annual report (paid indicator in reports list)
    annual_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("annual_reports.id"), nullable=True, index=True
    )

    # ── Core fields ───────────────────────────────────────────────────────────
    charge_type: Mapped[ChargeType] = mapped_column(pg_enum(ChargeType), nullable=False)
    status: Mapped[ChargeStatus] = mapped_column(
        pg_enum(ChargeStatus), default=ChargeStatus.DRAFT, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,  # Always ₪, no currency column
    )

    # ── Period ────────────────────────────────────────────────────────────────
    period: Mapped[str | None] = mapped_column(
        String(7),
        nullable=True,
        index=True,  # "YYYY-MM" — first month of coverage
    )
    months_covered: Mapped[int] = mapped_column(
        default=1,
        nullable=False,  # How many months this charge covers
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Lifecycle timestamps + actors ─────────────────────────────────────────
    created_at: Mapped[datetime.datetime] = mapped_column(default=utcnow, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    issued_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    paid_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    paid_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    canceled_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    canceled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Soft delete ───────────────────────────────────────────────────────────
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    annual_report: Mapped["AnnualReport | None"] = relationship(
        "AnnualReport", foreign_keys="[Charge.annual_report_id]", viewonly=True
    )
    invoice: Mapped["Invoice | None"] = relationship(
        "Invoice", foreign_keys="[Invoice.charge_id]", uselist=False
    )

    __table_args__ = (
        Index("idx_charge_client_record_period", "client_record_id", "period"),
        Index("idx_charge_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Charge(id={self.id}, client_record_id={self.client_record_id}, "
            f"business_id={self.business_id}, type='{self.charge_type}', "
            f"amount={self.amount}, status='{self.status}')>"
        )
