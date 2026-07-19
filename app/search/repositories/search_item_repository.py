from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder, BinderLocationStatus
from app.charges.models.charge import Charge
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.tasks.models.task import Task
from app.vat.models.vat_work_item import VatWorkItem

_ITEM_LIMIT = 5


@dataclass(frozen=True)
class SearchItemRow:
    id: int
    client_record_id: int
    office_client_number: int
    client_name: str
    status: str
    key: str
    detail: str | None = None
    amount: Decimal | None = None


class SearchItemRepository:
    def __init__(self, db: Session):
        self._db = db

    @staticmethod
    def _client_scope(stmt, model, client_scope: Select[tuple[int]]):
        stmt = stmt.join(ClientRecord, ClientRecord.id == model.client_record_id)
        stmt = stmt.join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id).where(
            ClientRecord.deleted_at.is_(None), ClientRecord.id.in_(client_scope)
        )
        return stmt

    @staticmethod
    def _identity_match(term: str):
        pattern = f"%{term}%"
        return or_(
            func.lower(LegalEntity.official_name).like(pattern),
            func.lower(LegalEntity.id_number).like(pattern),
            cast(ClientRecord.office_client_number, String).like(pattern),
            exists(
                select(Binder.id).where(
                    Binder.client_record_id == ClientRecord.id,
                    Binder.deleted_at.is_(None),
                    Binder.location_status != BinderLocationStatus.HANDED_OVER,
                    func.lower(Binder.binder_number).like(pattern),
                )
            ),
        )

    def _rows(self, stmt, count_stmt, mapper) -> tuple[list[SearchItemRow], int]:
        total = self._db.scalar(count_stmt) or 0
        rows = list(self._db.execute(stmt.limit(_ITEM_LIMIT)).all())
        return [mapper(row) for row in rows], total

    @staticmethod
    def _select(model):
        return select(
            model,
            ClientRecord.office_client_number.label("office_client_number"),
            LegalEntity.official_name.label("client_name"),
        )

    def search_tasks(
        self, term: str | None, client_scope: Select[tuple[int]]
    ) -> tuple[list[SearchItemRow], int]:
        base = self._client_scope(self._select(Task), Task, client_scope).where(
            Task.deleted_at.is_(None)
        )
        count = self._client_scope(
            select(func.count(Task.id)).select_from(Task), Task, client_scope
        ).where(Task.deleted_at.is_(None))
        if term:
            pattern = f"%{term}%"
            match = or_(
                self._identity_match(term),
                func.lower(Task.title).like(pattern),
                func.lower(func.coalesce(Task.description, "")).like(pattern),
                cast(Task.id, String).like(pattern),
            )
            base = base.where(match)
            count = count.where(match)
        return self._rows(
            base.order_by(Task.updated_at.desc(), Task.id.desc()),
            count,
            lambda result: SearchItemRow(
                id=result.Task.id,
                client_record_id=result.Task.client_record_id,
                office_client_number=result.office_client_number,
                client_name=result.client_name,
                status=result.Task.status.value,
                key=result.Task.title,
                detail=result.Task.description,
            ),
        )

    def search_vat(
        self, term: str | None, client_scope: Select[tuple[int]]
    ) -> tuple[list[SearchItemRow], int]:
        base = self._client_scope(self._select(VatWorkItem), VatWorkItem, client_scope).where(
            VatWorkItem.deleted_at.is_(None)
        )
        count = self._client_scope(
            select(func.count(VatWorkItem.id)).select_from(VatWorkItem),
            VatWorkItem,
            client_scope,
        ).where(VatWorkItem.deleted_at.is_(None))
        if term:
            pattern = f"%{term}%"
            match = or_(
                self._identity_match(term),
                VatWorkItem.period.like(pattern),
                cast(VatWorkItem.id, String).like(pattern),
            )
            base = base.where(match)
            count = count.where(match)
        return self._rows(
            base.order_by(VatWorkItem.period.desc(), VatWorkItem.id.desc()),
            count,
            lambda result: SearchItemRow(
                id=result.VatWorkItem.id,
                client_record_id=result.VatWorkItem.client_record_id,
                office_client_number=result.office_client_number,
                client_name=result.client_name,
                status=result.VatWorkItem.status.value,
                key=result.VatWorkItem.period,
                amount=result.VatWorkItem.final_vat_amount
                if result.VatWorkItem.final_vat_amount is not None
                else result.VatWorkItem.net_vat,
            ),
        )

    def search_annual_reports(
        self, term: str | None, client_scope: Select[tuple[int]]
    ) -> tuple[list[SearchItemRow], int]:
        base = self._client_scope(self._select(AnnualReport), AnnualReport, client_scope).where(
            AnnualReport.deleted_at.is_(None)
        )
        count = self._client_scope(
            select(func.count(AnnualReport.id)).select_from(AnnualReport),
            AnnualReport,
            client_scope,
        ).where(AnnualReport.deleted_at.is_(None))
        if term:
            pattern = f"%{term}%"
            match = or_(
                self._identity_match(term),
                cast(AnnualReport.tax_year, String).like(pattern),
                cast(AnnualReport.id, String).like(pattern),
                func.lower(func.coalesce(AnnualReport.ita_reference, "")).like(pattern),
            )
            base = base.where(match)
            count = count.where(match)
        return self._rows(
            base.order_by(AnnualReport.tax_year.desc(), AnnualReport.id.desc()),
            count,
            lambda result: SearchItemRow(
                id=result.AnnualReport.id,
                client_record_id=result.AnnualReport.client_record_id,
                office_client_number=result.office_client_number,
                client_name=result.client_name,
                status=result.AnnualReport.status.value,
                key=str(result.AnnualReport.tax_year),
                detail=result.AnnualReport.ita_reference,
            ),
        )

    def search_charges(
        self, term: str | None, client_scope: Select[tuple[int]]
    ) -> tuple[list[SearchItemRow], int]:
        base = self._client_scope(self._select(Charge), Charge, client_scope).where(
            Charge.deleted_at.is_(None)
        )
        count = self._client_scope(
            select(func.count(Charge.id)).select_from(Charge), Charge, client_scope
        ).where(Charge.deleted_at.is_(None))
        if term:
            pattern = f"%{term}%"
            match = or_(
                self._identity_match(term),
                cast(Charge.id, String).like(pattern),
                func.lower(func.coalesce(Charge.description, "")).like(pattern),
                func.coalesce(Charge.period, "").like(pattern),
            )
            base = base.where(match)
            count = count.where(match)
        return self._rows(
            base.order_by(Charge.created_at.desc(), Charge.id.desc()),
            count,
            lambda result: SearchItemRow(
                id=result.Charge.id,
                client_record_id=result.Charge.client_record_id,
                office_client_number=result.office_client_number,
                client_name=result.client_name,
                status=result.Charge.status.value,
                key=result.Charge.period or str(result.Charge.id),
                detail=result.Charge.description,
                amount=result.Charge.amount,
            ),
        )

    def search_advance_payments(
        self, term: str | None, client_scope: Select[tuple[int]]
    ) -> tuple[list[SearchItemRow], int]:
        base = self._client_scope(self._select(AdvancePayment), AdvancePayment, client_scope).where(
            AdvancePayment.deleted_at.is_(None)
        )
        count = self._client_scope(
            select(func.count(AdvancePayment.id)).select_from(AdvancePayment),
            AdvancePayment,
            client_scope,
        ).where(AdvancePayment.deleted_at.is_(None))
        if term:
            pattern = f"%{term}%"
            match = or_(
                self._identity_match(term),
                AdvancePayment.period.like(pattern),
                cast(AdvancePayment.id, String).like(pattern),
                func.lower(func.coalesce(AdvancePayment.notes, "")).like(pattern),
            )
            base = base.where(match)
            count = count.where(match)
        return self._rows(
            base.order_by(AdvancePayment.period.desc(), AdvancePayment.id.desc()),
            count,
            lambda result: SearchItemRow(
                id=result.AdvancePayment.id,
                client_record_id=result.AdvancePayment.client_record_id,
                office_client_number=result.office_client_number,
                client_name=result.client_name,
                status=result.AdvancePayment.status.value,
                key=result.AdvancePayment.period,
                detail=result.AdvancePayment.notes,
                amount=result.AdvancePayment.expected_amount,
            ),
        )
