"""Record matching for the typed term, across every domain in one UNION ALL.

One branch builder is the single source of each type's SELECT — match predicate,
projection, and scoping. The grouped preview, the per-type totals, and the paginated
expansion all derive from the same branches, so they cannot drift apart.

Phase 1 is exact match only (spec §3.2/§9): every predicate is equality, every row is
rank tier 1. The rank column exists in the SQL from day one so phase 2 adds tiers, not
structure.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import (
    Date,
    Integer,
    Numeric,
    Select,
    String,
    cast,
    func,
    literal,
    null,
    nullslast,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models.annual_report_model import AnnualReport
from app.binders.models.binder import Binder
from app.charges.models.charge import Charge
from app.clients.models.client_record import ClientRecord
from app.common.repositories.base_repository import BaseRepository
from app.documents.permanent_documents.models.permanent_document import PermanentDocument
from app.legal_entities.models.legal_entity import LegalEntity
from app.notifications.models.notification import Notification
from app.search.schemas.search import SearchMatchType
from app.search.search_term_parser import ParsedSearchTerm
from app.tasks.models.task import Task
from app.vat.models.vat_work_item import VatWorkItem

_EXACT_RANK = 1


@dataclass(frozen=True)
class SearchMatchRow:
    """One matched record with its owning client's identity, shared by all types."""

    result_type: SearchMatchType
    id: int
    client_record_id: int
    client_name: str
    client_office_number: int | None
    key: str
    status: str | None = None
    detail: str | None = None
    amount: Decimal | None = None
    occurred_on: dt.date | None = None


class SearchMatchRepository:
    """Builds and runs the per-type match branches for a parsed term."""

    def __init__(self, db: Session):
        self._db = db

    # ── Branch construction ───────────────────────────────────────────────────

    def build_match_branch(
        self, result_type: SearchMatchType, term: ParsedSearchTerm
    ) -> Select | None:
        """The one SELECT for `result_type`, or None when no capability activates it."""
        builder = _BRANCH_BUILDERS[result_type]
        return builder(term)

    def _active_branches(self, term: ParsedSearchTerm) -> list[Select]:
        return [
            branch
            for result_type in SearchMatchType
            if (branch := self.build_match_branch(result_type, term)) is not None
        ]

    # ── Queries ───────────────────────────────────────────────────────────────

    def search_matches(
        self, term: ParsedSearchTerm, preview_limit: int
    ) -> tuple[list[SearchMatchRow], dict[SearchMatchType, int]]:
        """Up to `preview_limit` rows per type plus each type's exact total — one query.

        The total rides on every row as `count(*) OVER (PARTITION BY result_type)`,
        computed before the `row_number()` cut, so no second counts query is needed;
        a type with no rows simply has total 0.
        """
        branches = self._active_branches(term)
        if not branches:
            return [], {}

        union = branches[0].union_all(*branches[1:]) if len(branches) > 1 else branches[0]
        sq = union.subquery("matches")
        ordering = _match_ordering(sq)
        windowed = select(
            sq,
            func.row_number()
            .over(partition_by=sq.c.result_type, order_by=ordering)
            .label("row_index"),
            func.count().over(partition_by=sq.c.result_type).label("type_total"),
        ).subquery("windowed")
        stmt = (
            select(windowed)
            .where(windowed.c.row_index <= preview_limit)
            .order_by(windowed.c.result_type, windowed.c.row_index)
        )

        rows: list[SearchMatchRow] = []
        totals: dict[SearchMatchType, int] = {}
        for record in self._db.execute(stmt).all():
            row = _to_row(record)
            rows.append(row)
            totals[row.result_type] = int(record.type_total)
        return rows, totals

    def list_matches(
        self,
        term: ParsedSearchTerm,
        result_type: SearchMatchType,
        page: int,
        page_size: int,
    ) -> tuple[list[SearchMatchRow], int]:
        """One type's matches in full, ordered exactly like the preview."""
        branch = self.build_match_branch(result_type, term)
        if branch is None:
            return [], 0

        sq = branch.subquery("matches")
        total = int(self._db.scalar(select(func.count()).select_from(sq)) or 0)
        stmt = select(sq).order_by(*_match_ordering(sq))
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        return [_to_row(record) for record in self._db.execute(stmt).all()], total


def _match_ordering(sq) -> list:
    """Deterministic within-type order: tier, then most recent, nulls last, id tiebreak.

    `id DESC` keeps pagination stable across ties.
    """
    return [
        sq.c.rank.asc(),
        nullslast(sq.c.occurred_on.desc()),
        sq.c.id.desc(),
    ]


def _to_row(record) -> SearchMatchRow:
    return SearchMatchRow(
        result_type=SearchMatchType(record.result_type),
        id=record.id,
        client_record_id=record.client_record_id,
        client_name=record.client_name,
        client_office_number=record.client_office_number,
        key=record.key,
        status=record.status,
        detail=record.detail,
        amount=record.amount,
        occurred_on=record.occurred_on,
    )


def _projection(
    result_type: SearchMatchType,
    model,
    *,
    key,
    status,
    detail,
    amount,
    occurred_on,
):
    """The shared column list every branch must project, in one place.

    Every expression is coerced to the union's common type: enum statuses to their
    stored string values, anchors to Date, absent columns to typed NULLs. The anchors
    mix Date and DateTime columns; `func.date(...)` truncates them consistently.
    `rank` is the tier literal — phase 1 is exact-only, so always 1.
    """
    return [
        literal(result_type.value).label("result_type"),
        model.id.label("id"),
        ClientRecord.id.label("client_record_id"),
        LegalEntity.official_name.label("client_name"),
        ClientRecord.office_client_number.label("client_office_number"),
        cast(key, String).label("key"),
        (cast(status, String) if status is not None else cast(null(), String)).label("status"),
        (cast(detail, String) if detail is not None else cast(null(), String)).label("detail"),
        (amount if amount is not None else cast(null(), Numeric)).label("amount"),
        func.date(occurred_on, type_=Date).label("occurred_on"),
        literal(_EXACT_RANK, Integer).label("rank"),
    ]


def _branch(
    result_type: SearchMatchType,
    model,
    *,
    predicate,
    active,
    key,
    status,
    detail,
    amount=None,
    occurred_on,
) -> Select:
    """One type's SELECT: §3.2 predicate + shared projection + the type's scoping.

    Every branch keeps the same per-domain scoping the dossier queries had:
    the `ClientRecord.deleted_at IS NULL` join plus the type's own soft-delete rule.
    """
    return (
        select(
            *_projection(
                result_type,
                model,
                key=key,
                status=status,
                detail=detail,
                amount=amount,
                occurred_on=occurred_on,
            )
        )
        .select_from(model)
        .join(ClientRecord, ClientRecord.id == model.client_record_id)
        .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
        .where(ClientRecord.deleted_at.is_(None), *active, predicate)
    )


def _binder_branch(term: ParsedSearchTerm) -> Select | None:
    # A binder number is a user-visible identifier (D4): equality runs for every term.
    return _branch(
        SearchMatchType.BINDER,
        Binder,
        predicate=Binder.binder_number == term.raw,
        active=[Binder.deleted_at.is_(None)],
        key=Binder.binder_number,
        status=Binder.location_status,
        detail=Binder.notes,
        occurred_on=Binder.period_start,
    )


def _document_branch(term: ParsedSearchTerm) -> Select | None:
    if not term.activates_text:
        return None
    return _branch(
        SearchMatchType.DOCUMENT,
        PermanentDocument,
        predicate=PermanentDocument.original_filename == term.raw,
        active=[
            PermanentDocument.is_deleted.is_(False),
            PermanentDocument.superseded_by.is_(None),
        ],
        key=func.coalesce(
            PermanentDocument.original_filename, cast(PermanentDocument.document_type, String)
        ),
        status=None,
        detail=PermanentDocument.document_type,
        occurred_on=PermanentDocument.uploaded_at,
    )


def _vat_branch(term: ParsedSearchTerm) -> Select | None:
    if term.period is None:
        return None
    return _branch(
        SearchMatchType.VAT_WORK_ITEM,
        VatWorkItem,
        predicate=VatWorkItem.period == term.period,
        # Chain tip only: an amended period would otherwise be two hits, and the
        # per-type total counts it twice.
        active=[VatWorkItem.deleted_at.is_(None), VatWorkItem.chain_tip_clause()],
        key=VatWorkItem.period,
        status=VatWorkItem.status,
        detail=None,
        amount=func.coalesce(VatWorkItem.final_vat_amount, VatWorkItem.net_vat),
        occurred_on=VatWorkItem.due_date_effective,
    )


def _annual_report_branch(term: ParsedSearchTerm) -> Select | None:
    # `ita_reference` is a user-visible identifier string: equality runs for every
    # term, including bare digits. `tax_year` needs the plausible-year heuristic.
    predicates = [AnnualReport.ita_reference == term.raw]
    if term.tax_year is not None:
        predicates.append(AnnualReport.tax_year == term.tax_year)
    predicate = or_(*predicates)
    return _branch(
        SearchMatchType.ANNUAL_REPORT,
        AnnualReport,
        predicate=predicate,
        active=[AnnualReport.deleted_at.is_(None), AnnualReport.chain_tip_clause()],
        key=AnnualReport.tax_year,
        status=AnnualReport.status,
        detail=AnnualReport.ita_reference,
        occurred_on=AnnualReport.filing_deadline,
    )


def _advance_payment_branch(term: ParsedSearchTerm) -> Select | None:
    if term.period is None:
        return None
    return _branch(
        SearchMatchType.ADVANCE_PAYMENT,
        AdvancePayment,
        predicate=AdvancePayment.period == term.period,
        active=[AdvancePayment.deleted_at.is_(None), AdvancePayment.chain_tip_clause()],
        key=AdvancePayment.period,
        status=AdvancePayment.status,
        detail=AdvancePayment.notes,
        amount=AdvancePayment.expected_amount,
        occurred_on=AdvancePayment.due_date,
    )


def _charge_branch(term: ParsedSearchTerm) -> Select | None:
    if term.integer is None:
        return None
    return _branch(
        SearchMatchType.CHARGE,
        Charge,
        predicate=Charge.id == term.integer,
        active=[Charge.deleted_at.is_(None)],
        key=Charge.id,
        status=Charge.status,
        detail=Charge.description,
        amount=Charge.amount,
        occurred_on=func.coalesce(Charge.issued_at, Charge.created_at),
    )


def _task_branch(term: ParsedSearchTerm) -> Select | None:
    if not term.activates_text:
        return None
    return _branch(
        SearchMatchType.TASK,
        Task,
        predicate=Task.title == term.raw,
        active=[Task.deleted_at.is_(None)],
        key=Task.title,
        status=Task.status,
        detail=Task.description,
        occurred_on=func.coalesce(func.date(Task.due_date), func.date(Task.updated_at)),
    )


def _notification_branch(term: ParsedSearchTerm) -> Select | None:
    if not term.activates_text:
        return None
    # Notifications have no soft-delete; unscoped beyond the client join. The key is
    # the raw trigger value — the service maps it to its Hebrew label.
    return _branch(
        SearchMatchType.NOTIFICATION,
        Notification,
        predicate=Notification.recipient == term.raw,
        active=[],
        key=Notification.trigger,
        status=Notification.status,
        detail=func.coalesce(Notification.subject_snapshot, Notification.recipient),
        occurred_on=Notification.created_at,
    )


_BRANCH_BUILDERS = {
    SearchMatchType.BINDER: _binder_branch,
    SearchMatchType.DOCUMENT: _document_branch,
    SearchMatchType.VAT_WORK_ITEM: _vat_branch,
    SearchMatchType.ANNUAL_REPORT: _annual_report_branch,
    SearchMatchType.ADVANCE_PAYMENT: _advance_payment_branch,
    SearchMatchType.CHARGE: _charge_branch,
    SearchMatchType.TASK: _task_branch,
    SearchMatchType.NOTIFICATION: _notification_branch,
}
