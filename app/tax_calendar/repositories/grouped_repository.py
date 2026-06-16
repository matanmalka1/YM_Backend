from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.clients.models.client_record import ClientRecord
from app.clients.repositories.active_client_scope import scope_to_active_clients_stmt
from app.common.enums import ObligationType
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.vat.models.vat_work_item import VatWorkItem


@dataclass(frozen=True)
class GroupedItemRow:
    row: Any
    client: ClientRecord
    legal_entity: LegalEntity

    def __iter__(self):
        yield self.row
        yield self.client
        yield self.legal_entity


def _entry_sort_clauses():
    # periodic rows sort by their period; annual_report (period=NULL) sorts after
    # all months of the same tax_year using a synthetic '9999-99' sentinel.
    period_key_expr = func.coalesce(
        TaxCalendarEntry.period,
        func.cast(TaxCalendarEntry.tax_year, String) + "-99",
    )
    obligation_priority = case(
        (TaxCalendarEntry.obligation_type == ObligationType.VAT, 1),
        (TaxCalendarEntry.obligation_type == ObligationType.ADVANCE_PAYMENT, 2),
        (TaxCalendarEntry.obligation_type == ObligationType.ANNUAL_REPORT, 3),
        else_=9,
    )
    frequency_priority = case(
        (TaxCalendarEntry.period_months_count == 1, 1),
        (TaxCalendarEntry.period_months_count == 2, 2),
        else_=9,
    )
    return (
        TaxCalendarEntry.tax_year.asc(),
        period_key_expr.asc(),
        obligation_priority.asc(),
        frequency_priority.asc(),
        TaxCalendarEntry.due_date.asc(),
        TaxCalendarEntry.id.asc(),
    )


class TaxCalendarGroupedRepository(BaseRepository[TaxCalendarEntry]):
    def __init__(self, db: Session):
        self.db = db

    def list_entries(
        self,
        *,
        tax_year_after: int | None,
        tax_year_before: int | None,
        obligation_type: ObligationType | None,
    ) -> list[TaxCalendarEntry]:
        stmt = select(TaxCalendarEntry)
        if tax_year_after is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year >= tax_year_after)
        if tax_year_before is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year <= tax_year_before)
        if obligation_type is not None:
            stmt = stmt.where(TaxCalendarEntry.obligation_type == obligation_type)
        else:
            stmt = stmt.where(
                TaxCalendarEntry.obligation_type.in_(
                    [
                        ObligationType.VAT,
                        ObligationType.ADVANCE_PAYMENT,
                        ObligationType.ANNUAL_REPORT,
                    ]
                )
            )
        return self.db.scalars(stmt.order_by(*_entry_sort_clauses())).all()

    def list_vat_for_entries(
        self,
        *,
        tax_year_after: int | None,
        tax_year_before: int | None,
        obligation_type: ObligationType | None,
        client_record_id: int | None = None,
        client_search: str | None = None,
    ) -> list[VatWorkItem]:
        if obligation_type is not None and obligation_type != ObligationType.VAT:
            return []
        stmt = (
            select(VatWorkItem)
            .join(
                TaxCalendarEntry,
                TaxCalendarEntry.id == VatWorkItem.tax_calendar_entry_id,
            )
            .where(TaxCalendarEntry.obligation_type == ObligationType.VAT)
            .where(VatWorkItem.deleted_at.is_(None))
        )
        stmt = self._apply_calendar_filters(stmt, tax_year_after, tax_year_before)
        stmt = scope_to_active_clients_stmt(stmt, VatWorkItem, join_legal_entity=True)
        if client_record_id is not None:
            stmt = stmt.where(VatWorkItem.client_record_id == client_record_id)
        stmt = self._apply_client_search(stmt, VatWorkItem, client_search)
        return self.db.scalars(stmt).all()

    def list_advance_for_entries(
        self,
        *,
        tax_year_after: int | None,
        tax_year_before: int | None,
        obligation_type: ObligationType | None,
        client_record_id: int | None = None,
        client_search: str | None = None,
    ) -> list[AdvancePayment]:
        if obligation_type is not None and obligation_type != ObligationType.ADVANCE_PAYMENT:
            return []
        stmt = (
            select(AdvancePayment)
            .join(
                TaxCalendarEntry,
                TaxCalendarEntry.id == AdvancePayment.tax_calendar_entry_id,
            )
            .where(TaxCalendarEntry.obligation_type == ObligationType.ADVANCE_PAYMENT)
            .where(AdvancePayment.deleted_at.is_(None))
        )
        stmt = self._apply_calendar_filters(stmt, tax_year_after, tax_year_before)
        stmt = scope_to_active_clients_stmt(stmt, AdvancePayment, join_legal_entity=True)
        if client_record_id is not None:
            stmt = stmt.where(AdvancePayment.client_record_id == client_record_id)
        stmt = self._apply_client_search(stmt, AdvancePayment, client_search)
        return self.db.scalars(stmt).all()

    def list_annual_for_entries(
        self,
        *,
        tax_year_after: int | None,
        tax_year_before: int | None,
        obligation_type: ObligationType | None,
        client_record_id: int | None = None,
        client_search: str | None = None,
    ) -> list[AnnualReport]:
        if obligation_type is not None and obligation_type != ObligationType.ANNUAL_REPORT:
            return []
        stmt = (
            select(AnnualReport)
            .join(
                TaxCalendarEntry,
                TaxCalendarEntry.id == AnnualReport.tax_calendar_entry_id,
            )
            .where(TaxCalendarEntry.obligation_type == ObligationType.ANNUAL_REPORT)
            .where(AnnualReport.deleted_at.is_(None))
        )
        stmt = self._apply_calendar_filters(stmt, tax_year_after, tax_year_before)
        stmt = scope_to_active_clients_stmt(stmt, AnnualReport, join_legal_entity=True)
        if client_record_id is not None:
            stmt = stmt.where(AnnualReport.client_record_id == client_record_id)
        stmt = self._apply_client_search(stmt, AnnualReport, client_search)
        return self.db.scalars(stmt).all()

    @staticmethod
    def _apply_calendar_filters(stmt, tax_year_after: int | None, tax_year_before: int | None):
        if tax_year_after is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year >= tax_year_after)
        if tax_year_before is not None:
            stmt = stmt.where(TaxCalendarEntry.tax_year <= tax_year_before)
        return stmt

    @staticmethod
    def _apply_client_search(stmt, model, client_search: str | None):
        if not client_search:
            return stmt
        like = f"%{client_search.strip()}%"
        return stmt.where(
            LegalEntity.official_name.ilike(like)
            | LegalEntity.id_number.ilike(like)
            | cast(ClientRecord.office_client_number, String).ilike(like)
        )

    def get_entry(self, entry_id: int) -> TaxCalendarEntry | None:
        return self.db.get(TaxCalendarEntry, entry_id)

    def list_vat_items(
        self,
        entry_id: int,
        *,
        client_search: str | None = None,
        client_record_id: int | None = None,
    ) -> list[GroupedItemRow]:
        return self._fetch_items(
            VatWorkItem,
            entry_id,
            client_search=client_search,
            client_record_id=client_record_id,
        )

    def list_advance_items(
        self,
        entry_id: int,
        *,
        client_search: str | None = None,
        client_record_id: int | None = None,
    ) -> list[GroupedItemRow]:
        return self._fetch_items(
            AdvancePayment,
            entry_id,
            client_search=client_search,
            client_record_id=client_record_id,
        )

    def list_annual_items(
        self,
        entry_id: int,
        *,
        client_search: str | None = None,
        client_record_id: int | None = None,
    ) -> list[GroupedItemRow]:
        return self._fetch_items(
            AnnualReport,
            entry_id,
            client_search=client_search,
            client_record_id=client_record_id,
        )

    def _fetch_items(
        self,
        model,
        entry_id: int,
        *,
        client_search: str | None,
        client_record_id: int | None,
    ) -> list[GroupedItemRow]:
        stmt = self._with_client(model).where(
            model.tax_calendar_entry_id == entry_id,
            model.deleted_at.is_(None),
        )
        if client_record_id is not None:
            stmt = stmt.where(model.client_record_id == client_record_id)
        stmt = self._apply_client_search(stmt, model, client_search)
        rows = self.db.execute(stmt).all()
        return [GroupedItemRow(row=r[0], client=r[1], legal_entity=r[2]) for r in rows]

    def _with_client(self, model):
        stmt = scope_to_active_clients_stmt(
            select(model, ClientRecord, LegalEntity), model, join_legal_entity=True
        )
        return stmt.order_by(ClientRecord.office_client_number.asc(), model.id.asc())
