"""Repository for client-level VAT summary queries."""

from decimal import Decimal

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_enums import InvoiceType, VatWorkItemStatus
from app.vat.models.vat_invoice import VatInvoice
from app.vat.models.vat_work_item import VatWorkItem


class VatClientSummaryRepository(BaseRepository[VatWorkItem]):
    def __init__(self, db: Session):
        self.db = db

    def get_annual_output_vat(
        self,
        client_record_id: int,
        year: int,
    ):
        return self.db.scalar(
            select(func.sum(VatWorkItem.total_output_vat)).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.period.like(f"{year}-%"),
                VatWorkItem.status == VatWorkItemStatus.FILED,
                VatWorkItem.deleted_at.is_(None),
            )
        )

    def get_periods_for_client(
        self,
        client_record_id: int,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[tuple]:
        net_sq = (
            select(
                VatInvoice.work_item_id,
                func.sum(
                    case(
                        (
                            VatInvoice.invoice_type == InvoiceType.INCOME,
                            VatInvoice.net_amount,
                        ),
                        else_=0,
                    )
                ).label("output_net"),
                func.sum(
                    case(
                        (
                            VatInvoice.invoice_type == InvoiceType.EXPENSE,
                            VatInvoice.net_amount,
                        ),
                        else_=0,
                    )
                ).label("input_net"),
            )
            .group_by(VatInvoice.work_item_id)
            .subquery()
        )

        stmt = (
            select(
                VatWorkItem,
                func.coalesce(net_sq.c.output_net, 0).label("output_net"),
                func.coalesce(net_sq.c.input_net, 0).label("input_net"),
            )
            .outerjoin(net_sq, VatWorkItem.id == net_sq.c.work_item_id)
            .where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.deleted_at.is_(None),
            )
        )
        if from_year is not None:
            stmt = stmt.where(func.substr(VatWorkItem.period, 1, 4) >= str(from_year))
        if to_year is not None:
            stmt = stmt.where(func.substr(VatWorkItem.period, 1, 4) <= str(to_year))
        return self.db.execute(stmt.order_by(VatWorkItem.period.desc())).all()

    def get_annual_turnover(self, client_record_id: int, year: int):
        """Sum of total_output_net for FILED work items in the given calendar year.

        Returns the scalar sum (Decimal or None if no FILED items exist).
        """
        return self.db.scalar(
            select(func.sum(VatWorkItem.total_output_net)).where(
                VatWorkItem.client_record_id == client_record_id,
                VatWorkItem.period.like(f"{year}-%"),
                VatWorkItem.status == VatWorkItemStatus.FILED,
                VatWorkItem.deleted_at.is_(None),
            )
        )

    def get_annual_turnover_by_client_ids(
        self,
        client_record_ids: list[int],
        year: int,
    ) -> dict[int, Decimal]:
        if not client_record_ids:
            return {}

        rows = self.db.execute(
            select(
                VatWorkItem.client_record_id,
                func.sum(VatWorkItem.total_output_net),
            )
            .where(
                VatWorkItem.client_record_id.in_(client_record_ids),
                VatWorkItem.period >= f"{year}-01",
                VatWorkItem.period <= f"{year}-12",
                VatWorkItem.status == VatWorkItemStatus.FILED,
                VatWorkItem.deleted_at.is_(None),
            )
            .group_by(VatWorkItem.client_record_id)
        ).all()
        return dict(rows)

    def get_annual_aggregates(
        self,
        client_record_id: int,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[dict[str, object]]:
        year_expr = cast(func.substr(VatWorkItem.period, 1, 4), Integer).label("year")
        stmt = select(
            year_expr,
            func.sum(VatWorkItem.total_output_vat).label("total_output_vat"),
            func.sum(VatWorkItem.total_input_vat).label("total_input_vat"),
            func.sum(VatWorkItem.net_vat).label("net_vat"),
            func.count(VatWorkItem.id).label("periods_count"),
            func.sum(case((VatWorkItem.status == VatWorkItemStatus.FILED, 1), else_=0)).label(
                "filed_count"
            ),
        ).where(
            VatWorkItem.client_record_id == client_record_id,
            VatWorkItem.deleted_at.is_(None),
        )
        if from_year is not None:
            stmt = stmt.where(func.substr(VatWorkItem.period, 1, 4) >= str(from_year))
        if to_year is not None:
            stmt = stmt.where(func.substr(VatWorkItem.period, 1, 4) <= str(to_year))
        rows = self.db.execute(stmt.group_by(year_expr).order_by(year_expr.desc())).all()

        return [
            {
                "year": row.year,
                "total_output_vat": row.total_output_vat,
                "total_input_vat": row.total_input_vat,
                "net_vat": row.net_vat,
                "periods_count": row.periods_count,
                "filed_count": row.filed_count,
            }
            for row in rows
        ]
