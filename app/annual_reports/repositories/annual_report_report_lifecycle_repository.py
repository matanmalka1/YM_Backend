"""Lifecycle/season operations for AnnualReport entities."""

import datetime as _dt
from decimal import Decimal

from sqlalchemy import func, select

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.models.annual_report_model import AnnualReport
from app.clients.repositories.client_active_scope import scope_to_active_clients_stmt
from app.utils.time_utils import israel_today, utcnow

DASHBOARD_FINAL_STATUSES = frozenset(
    {
        AnnualReportStatus.SUBMITTED,
        AnnualReportStatus.CLOSED,
        AnnualReportStatus.CANCELED,
    }
)


class AnnualReportLifecycleRepository:
    def _active_client_stmt(self):
        return scope_to_active_clients_stmt(select(AnnualReport), AnnualReport)

    def list_overdue(
        self, tax_year: int | None = None, page: int = 1, page_size: int = 20
    ) -> list[AnnualReport]:
        stmt = self._overdue_stmt(tax_year=tax_year)
        stmt = stmt.order_by(AnnualReport.filing_deadline.asc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count_overdue(self, tax_year: int | None = None) -> int:
        overdue_ids = self._overdue_stmt(tax_year=tax_year).with_only_columns(AnnualReport.id)
        return self.db.scalar(select(func.count()).select_from(overdue_ids.subquery())) or 0

    def _overdue_stmt(self, tax_year: int | None = None):
        now = utcnow()
        open_statuses = [
            AnnualReportStatus.NOT_STARTED,
            AnnualReportStatus.COLLECTING_DOCS,
            AnnualReportStatus.IN_PREPARATION,
            AnnualReportStatus.PENDING_CLIENT,
        ]
        stmt = self._active_client_stmt().where(
            AnnualReport.status.in_(open_statuses),
            AnnualReport.filing_deadline < now,
            AnnualReport.filing_deadline.isnot(None),
            AnnualReport.deleted_at.is_(None),
        )
        if tax_year:
            stmt = stmt.where(AnnualReport.tax_year == tax_year)
        return stmt

    def sum_financials_by_year(self, tax_year: int) -> dict:
        stmt = scope_to_active_clients_stmt(
            select(
                func.coalesce(func.sum(AnnualReport.refund_due), 0).label("total_refund_due"),
                func.coalesce(func.sum(AnnualReport.tax_due), 0).label("total_tax_due"),
            ),
            AnnualReport,
        ).where(
            AnnualReport.tax_year == tax_year,
            AnnualReport.deleted_at.is_(None),
        )
        row = self.db.execute(stmt).one()
        return {
            "total_refund_due": Decimal(str(row.total_refund_due)),
            "total_tax_due": Decimal(str(row.total_tax_due)),
        }

    def list_stuck_reports(self, stale_days: int = 7, limit: int = 3) -> list[AnnualReport]:
        """Return reports stuck in PENDING_CLIENT or COLLECTING_DOCS for >= stale_days."""
        cutoff = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=stale_days)
        stmt = (
            self._active_client_stmt()
            .where(
                AnnualReport.status.in_(
                    [
                        AnnualReportStatus.PENDING_CLIENT,
                        AnnualReportStatus.COLLECTING_DOCS,
                    ]
                ),
                AnnualReport.deleted_at.is_(None),
                AnnualReport.updated_at <= cutoff,
            )
            .order_by(AnnualReport.updated_at.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_for_dashboard(self, limit: int = 50) -> list[AnnualReport]:
        """Return non-final reports with a filing_deadline set, ordered by deadline asc.
        Excludes reports older than 2 years to avoid unsupported tax year errors."""
        cutoff = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=730)
        stmt = (
            self._active_client_stmt()
            .where(
                AnnualReport.status.notin_(list(DASHBOARD_FINAL_STATUSES)),
                AnnualReport.filing_deadline.isnot(None),
                AnnualReport.filing_deadline >= cutoff,
                AnnualReport.deleted_at.is_(None),
            )
            .order_by(AnnualReport.filing_deadline.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_default_tax_year_candidate(self) -> AnnualReport | None:
        stmt = (
            self._active_client_stmt()
            .where(
                AnnualReport.status.notin_(list(DASHBOARD_FINAL_STATUSES)),
                AnnualReport.filing_deadline.isnot(None),
                AnnualReport.filing_deadline >= israel_today(),
                AnnualReport.deleted_at.is_(None),
            )
            .order_by(AnnualReport.filing_deadline.asc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def get_latest_tax_year(self) -> int | None:
        stmt = scope_to_active_clients_stmt(
            select(func.max(AnnualReport.tax_year)), AnnualReport
        ).where(AnnualReport.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def get_season_summary(self, tax_year: int) -> dict:
        stmt = (
            scope_to_active_clients_stmt(
                select(AnnualReport.status, func.count(AnnualReport.id).label("cnt")),
                AnnualReport,
            )
            .where(
                AnnualReport.tax_year == tax_year,
                AnnualReport.deleted_at.is_(None),
            )
            .group_by(AnnualReport.status)
        )
        rows = self.db.execute(stmt).all()
        summary = {s.value: 0 for s in AnnualReportStatus}
        total = 0
        for row in rows:
            summary[row.status.value] += row.cnt
            total += row.cnt
        summary["total"] = total
        return summary


__all__ = ["AnnualReportLifecycleRepository"]
