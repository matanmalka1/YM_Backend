from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.annual_reports.models.annual_report_credit_point_reason import AnnualReportCreditPoint
    from app.annual_reports.models.annual_report_detail import AnnualReportDetail
    from app.annual_reports.models.annual_report_expense_line import AnnualReportExpenseLine
    from app.annual_reports.models.annual_report_income_line import AnnualReportIncomeLine
    from app.annual_reports.models.annual_report_schedule_entry import AnnualReportScheduleEntry

from app.annual_reports.models.annual_report_enums import (
    ClientAnnualFilingType,
    ExtensionReason,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
    SubmissionMethod,
)
from app.common.enums import ObligationStatus
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow

# ─── AnnualReport ─────────────────────────────────────────────────────────────


class AnnualReport(Base):
    __tablename__ = "annual_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_record_id: Mapped[int] = mapped_column(
        ForeignKey("client_records.id"), nullable=False, index=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    tax_year: Mapped[int] = mapped_column(nullable=False)
    client_type: Mapped[ClientAnnualFilingType] = mapped_column(
        pg_enum(ClientAnnualFilingType), nullable=False
    )
    # Snapshot of the main annual-return form derived from client_type at creation.
    form_type: Mapped[PrimaryAnnualReportForm] = mapped_column(
        pg_enum(PrimaryAnnualReportForm), nullable=False
    )
    status: Mapped[ObligationStatus] = mapped_column(
        pg_enum(ObligationStatus),
        default=ObligationStatus.AWAITING_INPUT,
        nullable=False,
    )

    deadline_type: Mapped[FilingDeadlineType] = mapped_column(
        pg_enum(FilingDeadlineType), default=FilingDeadlineType.STANDARD, nullable=False
    )
    filing_deadline: Mapped[datetime | None] = mapped_column(nullable=True)
    custom_deadline_note: Mapped[str | None] = mapped_column(String, nullable=True)

    # Closing facts (set when status → SUBMITTED)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # NULL means "no due date at close" (D-32), never "unknown" — written once, at the close
    closed_late: Mapped[bool | None] = mapped_column(nullable=True)
    ita_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    assessment_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    refund_due: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax_due: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    has_rental_income: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_capital_gains: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_foreign_income: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_depreciation: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_exempt_rental: Mapped[bool] = mapped_column(default=False, nullable=False)

    submission_method: Mapped[SubmissionMethod | None] = mapped_column(
        pg_enum(SubmissionMethod), nullable=True
    )
    extension_reason: Mapped[ExtensionReason | None] = mapped_column(
        pg_enum(ExtensionReason), nullable=True
    )

    tax_calendar_entry_id: Mapped[int] = mapped_column(
        ForeignKey("tax_calendar_entries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    detail: Mapped[AnnualReportDetail | None] = relationship(
        "AnnualReportDetail",
        back_populates="report",
        uselist=False,
        cascade="all, delete-orphan",
    )
    schedule_entries: Mapped[list[AnnualReportScheduleEntry]] = relationship(
        "AnnualReportScheduleEntry",
        back_populates="annual_report",
        cascade="all, delete-orphan",
    )
    income_lines: Mapped[list[AnnualReportIncomeLine]] = relationship(
        "AnnualReportIncomeLine",
        cascade="all, delete-orphan",
    )
    expense_lines: Mapped[list[AnnualReportExpenseLine]] = relationship(
        "AnnualReportExpenseLine",
        cascade="all, delete-orphan",
    )
    credit_points: Mapped[list[AnnualReportCreditPoint]] = relationship(
        "AnnualReportCreditPoint",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "idx_annual_report_client_record_year",
            "client_record_id",
            "tax_year",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_annual_report_status", "status"),
        Index(
            "idx_annual_report_tax_year_status_active",
            "tax_year",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_annual_report_calendar_entry_active",
            "tax_calendar_entry_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_annual_report_deadline", "filing_deadline"),
        Index("idx_annual_report_assigned", "assigned_to"),
        Index("idx_annual_report_ita_reference", "ita_reference"),
    )

    def __repr__(self):
        return (
            f"<AnnualReport(id={self.id}, client_record_id={self.client_record_id}, "
            f"year={self.tax_year}, status='{self.status}')>"
        )
