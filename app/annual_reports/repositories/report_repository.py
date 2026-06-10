"""Low-level DB repository for the AnnualReport aggregate root row."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
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
        return scope_to_active_clients_stmt(select(AnnualReport), AnnualReport)

    def list_by_client_record(
        self, client_record_id: int, page: int = 1, page_size: int = 20
    ) -> list[AnnualReport]:
        stmt = (
            select(AnnualReport)
            .where(
                AnnualReport.client_record_id == client_record_id,
                AnnualReport.deleted_at.is_(None),
            )
            .order_by(AnnualReport.tax_year.desc())
        )
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_by_client_record(self, client_record_id: int) -> int:
        return self.db.scalar(
            select(func.count(AnnualReport.id)).where(
                AnnualReport.client_record_id == client_record_id,
                AnnualReport.deleted_at.is_(None),
            )
        )

    def get_by_client_record_year(
        self, client_record_id: int, tax_year: int
    ) -> AnnualReport | None:
        return self.db.scalars(
            select(AnnualReport).where(
                AnnualReport.client_record_id == client_record_id,
                AnnualReport.tax_year == tax_year,
                AnnualReport.deleted_at.is_(None),
            )
        ).first()

    def list_by_status(
        self,
        status: AnnualReportStatus,
        tax_year: int | None = None,
        assigned_to: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[AnnualReport]:
        stmt = self._active_client_stmt().where(
            AnnualReport.status == status,
            AnnualReport.deleted_at.is_(None),
        )
        if tax_year:
            stmt = stmt.where(AnnualReport.tax_year == tax_year)
        if assigned_to:
            stmt = stmt.where(AnnualReport.assigned_to == assigned_to)
        stmt = stmt.order_by(AnnualReport.filing_deadline.asc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_by_status(
        self,
        status: AnnualReportStatus,
        tax_year: int | None = None,
    ) -> int:
        stmt = scope_to_active_clients_stmt(
            select(func.count(AnnualReport.id)), AnnualReport
        ).where(
            AnnualReport.status == status,
            AnnualReport.deleted_at.is_(None),
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
            .where(
                AnnualReport.tax_year == tax_year,
                AnnualReport.deleted_at.is_(None),
            )
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
            select(func.count(AnnualReport.id)), AnnualReport
        ).where(
            AnnualReport.tax_year == tax_year,
            AnnualReport.deleted_at.is_(None),
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
        stmt = (
            self._active_client_stmt()
            .where(
                AnnualReport.deleted_at.is_(None),
            )
            .order_by(_sort_col(sort_by, order))
        )
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
            select(func.count(AnnualReport.id)), AnnualReport
        ).where(AnnualReport.deleted_at.is_(None))
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        if status is not None:
            stmt = stmt.where(AnnualReport.status == status)
        return self.db.scalar(stmt)

    def list_by_tax_year_with_client(self, tax_year: int) -> list:
        """Return (AnnualReport, client_record_id, LegalEntity.official_name) for status report."""
        from app.clients.models.client_record import ClientRecord
        from app.legal_entities.models.legal_entity import LegalEntity

        return self.db.execute(
            select(AnnualReport, AnnualReport.client_record_id, LegalEntity.official_name)
            .join(ClientRecord, ClientRecord.id == AnnualReport.client_record_id)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(
                AnnualReport.tax_year == tax_year,
                AnnualReport.deleted_at.is_(None),
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
        terminal = [
            AnnualReportStatus.SUBMITTED,
            AnnualReportStatus.CLOSED,
            AnnualReportStatus.CANCELED,
        ]
        rows = self.db.scalars(
            select(AnnualReport).where(
                AnnualReport.client_record_id == client_record_id,
                AnnualReport.deleted_at.is_(None),
                AnnualReport.status.notin_(terminal),
            )
        ).all()
        for row in rows:
            row.status = AnnualReportStatus.CANCELED
            row.updated_at = utcnow()
        if rows:
            self.db.flush()
        return len(rows)
