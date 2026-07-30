"""Low-level DB repository for the AnnualReport aggregate root row."""

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_model import AnnualReport
from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.common.enums import RESOLVED_OBLIGATION_STATUSES, ObligationStatus
from app.common.obligation_chain import (
    copy_child,
    link_amendment,
    select_current_obligation,
    select_obligations,
    select_slot_occupant,
)
from app.common.repositories.base_repository import BaseRepository
from app.utils.time_utils import utcnow

_SORT_COLUMNS = {
    "tax_year": AnnualReport.tax_year,
    "status": AnnualReport.status,
    "filing_deadline": AnnualReport.filing_deadline,
    "created_at": AnnualReport.created_at,
    "client_record_id": AnnualReport.client_record_id,
}


def _sort_col(sort_by: str, order: str):
    col = _SORT_COLUMNS.get(sort_by, AnnualReport.created_at)
    return col.asc() if order == "asc" else col.desc()


class AnnualReportRootRepository(BaseRepository[AnnualReport]):
    model = AnnualReport

    def __init__(self, db: Session):
        super().__init__(db)

    # ── AnnualReport CRUD / queries ─────────────────────────────────────────

    def create(self, **kwargs) -> AnnualReport:
        return self.build_and_add(**kwargs)

    def _active_client_stmt(self):
        return scope_to_active_clients_stmt(select_obligations(AnnualReport), AnnualReport)

    def create_amendment(self, original: AnnualReport, *, fields: dict) -> AnnualReport:
        """Persist a correction of ``original``, with its whole material copied.

        ``fields`` arrives already decided by the service — what an amendment
        inherits and what it must not (D-14, D-21) is a domain question. What
        belongs here is that the copy is deep and atomic: the detail row, the
        income and expense lines, the credit-point reasons, and the schedule
        entries with their annex lines, in one flush. An annual report copied
        without its schedules is not a correction of anything.
        """
        amendment = AnnualReport(**fields)
        link_amendment(amendment, original)
        self.db.add(amendment)
        self.db.flush()

        if original.detail is not None:
            self.db.add(
                copy_child(original.detail, parent_fk="annual_report_id", parent_id=amendment.id)
            )
        for line in (*original.income_lines, *original.expense_lines, *original.credit_points):
            self.db.add(copy_child(line, parent_fk="annual_report_id", parent_id=amendment.id))

        for entry in original.schedule_entries:
            copied = copy_child(entry, parent_fk="annual_report_id", parent_id=amendment.id)
            self.db.add(copied)
            self.db.flush()
            for annex_line in entry.annex_lines:
                self.db.add(
                    copy_child(annex_line, parent_fk="schedule_entry_id", parent_id=copied.id)
                )
        self.db.flush()
        return amendment

    def list_due_for_work_queue(
        self, cutoff, client_record_id: int | None = None
    ) -> list[AnnualReport]:
        """Active-client reports that still need work: due by ``cutoff``, or undated.

        The deadline test admits a NULL. An amendment carries no filing deadline
        (D-14), and a deadline filter that simply excluded NULL would drop every
        open correction out of the one list whose purpose is to surface work
        nobody has finished — a live obligation, invisible. Undated rows are
        included and the work queue ranks them by other means; being late is not
        the only reason a report needs doing.
        """
        stmt = scope_to_active_clients_stmt(select_obligations(AnnualReport), AnnualReport).where(
            or_(
                AnnualReport.filing_deadline.is_(None),
                AnnualReport.filing_deadline <= cutoff,
            ),
            AnnualReport.status.notin_(RESOLVED_OBLIGATION_STATUSES),
        )
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        return list(self.db.scalars(stmt).all())

    def list_by_client_record(
        self, client_record_id: int, page: int = 1, page_size: int = 20
    ) -> list[AnnualReport]:
        stmt = (
            scope_to_active_clients_stmt(select_obligations(AnnualReport), AnnualReport)
            .where(
                AnnualReport.client_record_id == client_record_id,
            )
            .order_by(AnnualReport.tax_year.desc(), AnnualReport.id.desc())
        )
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_by_client_record(self, client_record_id: int) -> int:
        return self.db.scalar(
            scope_to_active_clients_stmt(
                select_obligations(AnnualReport, func.count(AnnualReport.id)), AnnualReport
            ).where(
                AnnualReport.client_record_id == client_record_id,
            )
        )

    def get_slot_occupant_for_year(
        self, client_record_id: int, tax_year: int
    ) -> AnnualReport | None:
        """The report holding this year's slot, for creation gates only."""
        return self.db.scalars(
            select_slot_occupant(
                AnnualReport,
                client_record_id=client_record_id,
                period_column=AnnualReport.tax_year,
                period_value=tax_year,
            )
        ).first()

    def get_by_client_record_year(
        self, client_record_id: int, tax_year: int
    ) -> AnnualReport | None:
        """The year's operational report — what it displays and what work acts on."""
        return self.db.scalars(
            select_current_obligation(
                AnnualReport,
                client_record_id=client_record_id,
                period_column=AnnualReport.tax_year,
                period_value=tax_year,
            )
        ).first()

    def list_by_status(
        self,
        status: ObligationStatus,
        tax_year: int | None = None,
        assigned_to: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[AnnualReport]:
        stmt = self._active_client_stmt().where(AnnualReport.status == status)
        if tax_year:
            stmt = stmt.where(AnnualReport.tax_year == tax_year)
        if assigned_to:
            stmt = stmt.where(AnnualReport.assigned_to == assigned_to)
        stmt = stmt.order_by(AnnualReport.filing_deadline.asc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_by_status(
        self,
        status: ObligationStatus,
        tax_year: int | None = None,
    ) -> int:
        stmt = scope_to_active_clients_stmt(
            select_obligations(AnnualReport, func.count(AnnualReport.id)), AnnualReport
        ).where(
            AnnualReport.status == status,
        )
        if tax_year:
            stmt = stmt.where(AnnualReport.tax_year == tax_year)
        return self.db.scalar(stmt)

    def list_by_tax_year(
        self,
        tax_year: int,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "status",
        order: str = "asc",
        client_record_id: int | None = None,
        status: str | None = None,
    ) -> list[AnnualReport]:
        stmt = (
            self._active_client_stmt()
            .where(AnnualReport.tax_year == tax_year)
            .order_by(_sort_col(sort_by, order))
        )
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        if status is not None:
            stmt = stmt.where(AnnualReport.status == status)
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_by_tax_year(
        self,
        tax_year: int,
        client_record_id: int | None = None,
        status: str | None = None,
    ) -> int:
        stmt = scope_to_active_clients_stmt(
            select_obligations(AnnualReport, func.count(AnnualReport.id)), AnnualReport
        ).where(
            AnnualReport.tax_year == tax_year,
        )
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        if status is not None:
            stmt = stmt.where(AnnualReport.status == status)
        return self.db.scalar(stmt)

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "tax_year",
        order: str = "desc",
        client_record_id: int | None = None,
        status: str | None = None,
    ) -> list[AnnualReport]:
        stmt = self._active_client_stmt().order_by(_sort_col(sort_by, order))
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        if status is not None:
            stmt = stmt.where(AnnualReport.status == status)
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_all(
        self,
        client_record_id: int | None = None,
        status: str | None = None,
    ) -> int:
        stmt = scope_to_active_clients_stmt(
            select_obligations(AnnualReport, func.count(AnnualReport.id)), AnnualReport
        )
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        if status is not None:
            stmt = stmt.where(AnnualReport.status == status)
        return self.db.scalar(stmt)

    def list_by_tax_year_with_client(self, tax_year: int) -> list:
        """Return annual reports with the client identity rendered by the status report."""
        from app.clients.models.client_record import ClientRecord
        from app.legal_entities.models.legal_entity import LegalEntity

        return self.db.execute(
            select_obligations(
                AnnualReport,
                AnnualReport,
                AnnualReport.client_record_id,
                LegalEntity.official_name,
                LegalEntity.id_number,
                ClientRecord.office_client_number,
            )
            .join(ClientRecord, ClientRecord.id == AnnualReport.client_record_id)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(
                AnnualReport.tax_year == tax_year,
                ClientRecord.deleted_at.is_(None),
            )
            .order_by(AnnualReport.filing_deadline.asc().nulls_last())
        ).all()

    def update(
        self, report_id: int, report: AnnualReport | None = None, **fields
    ) -> AnnualReport | None:
        """Update report fields. Pass a pre-fetched (optionally locked) ``report`` entity
        to avoid a second SELECT and keep the lock from get_by_id_for_update() alive."""
        entity = report or self.get_by_id(report_id)
        return self._update_entity(entity, touch_updated_at=True, **fields)

    def soft_delete(self, report_id: int, deleted_by: int | None = None) -> bool:
        return self._soft_delete_entity(report_id, deleted_by)

    def cancel_open_by_client_record(self, client_record_id: int) -> int:
        rows = self.db.scalars(
            select_obligations(AnnualReport).where(
                AnnualReport.client_record_id == client_record_id,
                AnnualReport.status.notin_(RESOLVED_OBLIGATION_STATUSES),
            )
        ).all()
        for row in rows:
            row.status = ObligationStatus.CANCELED
            row.updated_at = utcnow()
        if rows:
            self.db.flush()
        return len(rows)
