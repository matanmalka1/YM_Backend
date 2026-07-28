"""VAT's published answer to "what turnover can a span of months report?".

This is VAT's contract for consumers outside the domain. It exists because the rule
it encodes — *which* work-item statuses may be drawn from, and what counts as full
coverage of a span — is VAT's to define. It previously lived inside
``advance_payments``, which meant a change to VAT filing semantics silently changed
another domain's numbers with no signal on this side.

Two forms of the same rule, which must change together:

- :meth:`VatTurnoverRepository.resolve_spans` — the Python form, for reads that
  load rows.
- :func:`covering_work_items_select` + :func:`turnover_sum_expr` — the SQL form,
  for filtering a set the server never loads (a paginated list cannot be narrowed
  by a Python check).

What this module deliberately does *not* decide: how a consumer labels the
provenance of a figure it stores, or what counts as an acceptable difference from
one. Those belong to whoever owns the storing column.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Integer, cast, func, literal, select
from sqlalchemy.orm import Session

from app.common.period_utils import parse_period
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem

# FILED items are settled figures. READY_FOR_REVIEW ones can still change before
# filing, so they are resolvable but never count as settled.
FILED_STATUSES = (VatWorkItemStatus.FILED,)
UNFILED_STATUSES = (VatWorkItemStatus.READY_FOR_REVIEW,)
RESOLVABLE_STATUSES = (*FILED_STATUSES, *UNFILED_STATUSES)


def expand_span(period: str, months_count: int) -> list[str]:
    """The ``YYYY-MM`` months a span starting at ``period`` covers."""
    year, month = parse_period(period)
    result = []
    for offset in range(months_count):
        absolute = year * 12 + month - 1 + offset
        result.append(f"{absolute // 12}-{absolute % 12 + 1:02d}")
    return result


@dataclass(frozen=True)
class VatSpanTurnover:
    """VAT's reported turnover for one fully covered span of months.

    ``is_fully_filed`` is ``True`` only when every covering month is FILED. One
    unfiled month among them makes the combined figure worth no more than that
    weakest return, and the consumer is expected to treat it accordingly.
    """

    amount: Decimal
    is_fully_filed: bool
    vat_work_item_ids: list[int]


class VatTurnoverRepository:
    """Reads ``vat_work_items.total_output_net`` under VAT's coverage rule."""

    def __init__(self, db: Session):
        self.db = db

    def resolve_spans(
        self,
        spans_by_client: dict[int, list[tuple[str, int]]],
    ) -> dict[tuple[int, str], VatSpanTurnover | None]:
        """Resolve every requested span in one query, keyed by ``(client, period)``.

        A span resolves only when *every* month it covers has a resolvable work
        item; a half-covered bi-monthly span returns ``None`` rather than a
        silently halved turnover. Callers get an entry for every span they asked
        about, so a missing key means they did not ask.
        """
        if not spans_by_client:
            return {}

        wanted_months: set[str] = set()
        for spans in spans_by_client.values():
            for period, months_count in spans:
                wanted_months.update(expand_span(period, months_count))

        rows = self.db.execute(
            select(
                VatWorkItem.client_record_id,
                VatWorkItem.period,
                VatWorkItem.id,
                VatWorkItem.total_output_net,
                VatWorkItem.status,
            ).where(
                VatWorkItem.client_record_id.in_(spans_by_client),
                VatWorkItem.period.in_(wanted_months),
                VatWorkItem.status.in_(RESOLVABLE_STATUSES),
                VatWorkItem.deleted_at.is_(None),
            )
        ).all()
        # (client, period) is unique among non-deleted work items, so one row each.
        by_month = {(row.client_record_id, row.period): row for row in rows}

        resolved: dict[tuple[int, str], VatSpanTurnover | None] = {}
        for client_record_id, spans in spans_by_client.items():
            for period, months_count in spans:
                months = expand_span(period, months_count)
                covering = [
                    by_month[(client_record_id, month)]
                    for month in months
                    if (client_record_id, month) in by_month
                ]
                if len(covering) != len(months):
                    resolved[(client_record_id, period)] = None
                    continue
                resolved[(client_record_id, period)] = VatSpanTurnover(
                    amount=sum(
                        (Decimal(str(row.total_output_net)) for row in covering), Decimal("0")
                    ),
                    is_fully_filed=all(row.status in FILED_STATUSES for row in covering),
                    vat_work_item_ids=[row.id for row in covering],
                )
        return resolved


def turnover_sum_expr():
    """The aggregate a covered span's turnover is summed with, in SQL."""
    return func.sum(VatWorkItem.total_output_net)


def covering_work_items_select(*, client_record_id, period, months_count):
    """Correlated select over the work items covering a span, in SQL.

    Applies the same two halves of the rule as :meth:`VatTurnoverRepository.resolve_spans`:
    only resolvable statuses count, and the span must be *fully* covered
    (``HAVING count(...) = months_count``).

    The caller passes its own anchor columns, adds any further aggregate condition
    with ``.having(...)``, and correlates to its own table — this module does not
    know what the caller intends to compare against.

    Both months of a bi-monthly span fall in the span's own year, because
    bi-monthly periods start on an odd month, so months are compared within the
    year rather than by building an end-period string.
    """
    span_start_month = cast(func.substr(period, 6, 2), Integer)
    vat_month = cast(func.substr(VatWorkItem.period, 6, 2), Integer)
    return (
        select(literal(1))
        .select_from(VatWorkItem)
        .where(
            VatWorkItem.client_record_id == client_record_id,
            VatWorkItem.deleted_at.is_(None),
            VatWorkItem.status.in_(RESOLVABLE_STATUSES),
            func.substr(VatWorkItem.period, 1, 4) == func.substr(period, 1, 4),
            vat_month >= span_start_month,
            vat_month <= span_start_month + months_count - 1,
        )
        # One group: the WHERE already pins a single client.
        .group_by(VatWorkItem.client_record_id)
        .having(func.count(VatWorkItem.id) == months_count)
    )


__all__ = [
    "FILED_STATUSES",
    "RESOLVABLE_STATUSES",
    "UNFILED_STATUSES",
    "VatSpanTurnover",
    "VatTurnoverRepository",
    "covering_work_items_select",
    "expand_span",
    "turnover_sum_expr",
]
