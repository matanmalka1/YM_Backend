from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder
from app.charges.models.charge import Charge
from app.clients.models.client_record import ClientRecord
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.notifications.models.notification import TRIGGER_LABELS, Notification
from app.tasks.models.task import Task
from app.vat.models.vat_work_item import VatWorkItem


@dataclass(frozen=True)
class SearchItemRow:
    """One item of any type, already carrying its owning client's identity.

    `status` is None for types with no work status (documents). `occurred_on` is the date
    the row is anchored to — the same column the type is ordered by, so the feed reads
    chronologically within a type.
    """

    id: int
    client_record_id: int
    key: str
    status: str | None = None
    detail: str | None = None
    amount: Decimal | None = None
    occurred_on: dt.date | None = None


def _as_date(value: dt.datetime | dt.date | None) -> dt.date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, dt.datetime) else value


class SearchItemRepository:
    """Reads one client's items across every domain, in one shared row shape.

    Every query is anchored to a single `client_record_id`: the search flow resolves a
    client first, and the item feed then shows that client's records in full. There is
    no text filter here — narrowing happens by type in the UI.
    """

    def __init__(self, db: Session):
        self._db = db

    def _search(
        self,
        model: Any,
        *,
        client_record_id: int,
        active: Sequence[ColumnElement[bool]],
        order_by: Sequence[Any],
        mapper: Callable[[Any], SearchItemRow],
        limit: int,
        offset: int,
    ) -> tuple[list[SearchItemRow], int]:
        conditions = [
            model.client_record_id == client_record_id,
            ClientRecord.deleted_at.is_(None),
            *active,
        ]
        rows_stmt = (
            select(model)
            .join(ClientRecord, ClientRecord.id == model.client_record_id)
            .where(*conditions)
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
        count_stmt = (
            select(func.count(model.id))
            .select_from(model)
            .join(ClientRecord, ClientRecord.id == model.client_record_id)
            .where(*conditions)
        )
        total = int(self._db.scalar(count_stmt) or 0)
        rows = [mapper(result) for result in self._db.execute(rows_stmt).all()]
        return rows, total

    def search_binders(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            Binder,
            client_record_id=client_record_id,
            active=[Binder.deleted_at.is_(None)],
            order_by=[Binder.binder_number.desc(), Binder.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.Binder.id,
                client_record_id=result.Binder.client_record_id,
                key=result.Binder.binder_number,
                status=result.Binder.location_status.value,
                detail=result.Binder.notes,
                occurred_on=_as_date(result.Binder.period_start),
            ),
        )

    def search_documents(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            PermanentDocument,
            client_record_id=client_record_id,
            active=[
                PermanentDocument.is_deleted.is_(False),
                PermanentDocument.superseded_by.is_(None),
            ],
            order_by=[PermanentDocument.uploaded_at.desc(), PermanentDocument.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.PermanentDocument.id,
                client_record_id=result.PermanentDocument.client_record_id,
                key=result.PermanentDocument.original_filename
                or result.PermanentDocument.document_type.value,
                detail=result.PermanentDocument.document_type.value,
                occurred_on=_as_date(result.PermanentDocument.uploaded_at),
            ),
        )

    def search_vat(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            VatWorkItem,
            client_record_id=client_record_id,
            active=[VatWorkItem.deleted_at.is_(None)],
            order_by=[VatWorkItem.period.desc(), VatWorkItem.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.VatWorkItem.id,
                client_record_id=result.VatWorkItem.client_record_id,
                key=result.VatWorkItem.period,
                status=result.VatWorkItem.status.value,
                amount=result.VatWorkItem.final_vat_amount
                if result.VatWorkItem.final_vat_amount is not None
                else result.VatWorkItem.net_vat,
                occurred_on=_as_date(result.VatWorkItem.due_date_effective),
            ),
        )

    def search_annual_reports(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            AnnualReport,
            client_record_id=client_record_id,
            active=[AnnualReport.deleted_at.is_(None)],
            order_by=[AnnualReport.tax_year.desc(), AnnualReport.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.AnnualReport.id,
                client_record_id=result.AnnualReport.client_record_id,
                key=str(result.AnnualReport.tax_year),
                status=result.AnnualReport.status.value,
                detail=result.AnnualReport.ita_reference,
                occurred_on=_as_date(result.AnnualReport.filing_deadline),
            ),
        )

    def search_advance_payments(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            AdvancePayment,
            client_record_id=client_record_id,
            active=[AdvancePayment.deleted_at.is_(None)],
            order_by=[AdvancePayment.period.desc(), AdvancePayment.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.AdvancePayment.id,
                client_record_id=result.AdvancePayment.client_record_id,
                key=result.AdvancePayment.period,
                status=result.AdvancePayment.status.value,
                detail=result.AdvancePayment.notes,
                amount=result.AdvancePayment.expected_amount,
                occurred_on=_as_date(result.AdvancePayment.due_date),
            ),
        )

    def search_charges(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            Charge,
            client_record_id=client_record_id,
            active=[Charge.deleted_at.is_(None)],
            order_by=[Charge.created_at.desc(), Charge.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.Charge.id,
                client_record_id=result.Charge.client_record_id,
                key=str(result.Charge.id),
                status=result.Charge.status.value,
                detail=result.Charge.description,
                amount=result.Charge.amount,
                occurred_on=_as_date(result.Charge.issued_at or result.Charge.created_at),
            ),
        )

    def search_tasks(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            Task,
            client_record_id=client_record_id,
            active=[Task.deleted_at.is_(None)],
            order_by=[Task.updated_at.desc(), Task.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.Task.id,
                client_record_id=result.Task.client_record_id,
                key=result.Task.title,
                status=result.Task.status.value,
                detail=result.Task.description,
                occurred_on=_as_date(result.Task.due_date or result.Task.updated_at),
            ),
        )

    def search_notifications(
        self, client_record_id: int, *, limit: int, offset: int = 0
    ) -> tuple[list[SearchItemRow], int]:
        return self._search(
            Notification,
            client_record_id=client_record_id,
            active=[],
            order_by=[Notification.created_at.desc(), Notification.id.desc()],
            limit=limit,
            offset=offset,
            mapper=lambda result: SearchItemRow(
                id=result.Notification.id,
                client_record_id=result.Notification.client_record_id,
                key=TRIGGER_LABELS[result.Notification.trigger],
                status=result.Notification.status.value,
                detail=result.Notification.subject_snapshot or result.Notification.recipient,
                occurred_on=_as_date(result.Notification.created_at),
            ),
        )
