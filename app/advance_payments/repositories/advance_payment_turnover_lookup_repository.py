"""Advance-payment view of VAT's published turnover answer.

VAT owns the rule about *what a span of months can report*: which work-item
statuses may be drawn from, and what counts as full coverage. That rule lives in
``app.vat.repositories.vat_turnover_repository`` and is consumed here through its
published contract, never by re-reading VAT's tables.

This module owns only the advance-payment half:

- mapping VAT's settled/unsettled answer onto :class:`TurnoverSource`, the
  provenance enum stored on this domain's own column;
- deciding what counts as a mismatch against a stored ``turnover_amount``
  (:data:`VAT_TURNOVER_MISMATCH_TOLERANCE`).

:func:`vat_turnover_mismatch_expr` is the SQL form of that comparison, built on
VAT's SQL coverage rule. It exists because the overview is server-paginated, so a
Python check cannot back a filter. It and the Python path above must stay in
agreement: a row the list filters in must be a row the detail route flags.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.advance_payments.advance_payment_constants import VAT_TURNOVER_MISMATCH_TOLERANCE
from app.advance_payments.models.advance_payment import AdvancePayment, TurnoverSource
from app.vat.repositories.vat_turnover_repository import (
    VatTurnoverRepository,
    covering_work_items_select,
    turnover_sum_expr,
)


@dataclass(frozen=True)
class TurnoverResolution:
    """What an advance-payment period can draw from its VAT returns.

    ``source`` is ``None`` exactly when ``amount`` is ``None`` — the period is
    unresolved. It is never :attr:`TurnoverSource.MANUAL`; that value describes a
    figure an advisor typed, which by definition did not come from this lookup.
    """

    amount: Decimal | None
    source: TurnoverSource | None
    vat_work_item_ids: list[int]

    @property
    def is_resolved(self) -> bool:
        return self.amount is not None


_UNRESOLVED = TurnoverResolution(amount=None, source=None, vat_work_item_ids=[])


class TurnoverLookupRepository:
    """Resolve advance-payment periods against VAT's reported turnover."""

    def __init__(self, db: Session):
        self.db = db
        self._vat = VatTurnoverRepository(db)

    def resolve_turnover(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int = 1,
    ) -> TurnoverResolution:
        """Resolve a single period."""
        resolved = self.resolve_turnover_for_clients(
            {client_record_id: [(period, period_months_count)]}
        )
        return resolved[(client_record_id, period)]

    def resolve_turnover_for_client(
        self,
        client_record_id: int,
        periods: list[tuple[str, int]],
    ) -> dict[str, TurnoverResolution]:
        """Resolve many periods for one client, keyed by period."""
        if not periods:
            return {}
        resolved = self.resolve_turnover_for_clients({client_record_id: periods})
        return {period: resolved[(client_record_id, period)] for period, _ in periods}

    def resolve_turnover_for_clients(
        self,
        periods_by_client: dict[int, list[tuple[str, int]]],
    ) -> dict[tuple[int, str], TurnoverResolution]:
        """Resolve many periods across many clients, keyed by (client, period)."""
        spans = self._vat.resolve_spans(periods_by_client)
        return {key: _to_resolution(span) for key, span in spans.items()}


def _to_resolution(span) -> TurnoverResolution:
    """Label VAT's answer with this domain's provenance enum.

    A span VAT reports as fully filed is a settled figure (``vat_filed``); one
    with any unfiled month among its coverage is only ``vat_pending``, because the
    combined figure is worth no more than its weakest return.
    """
    if span is None:
        return _UNRESOLVED
    return TurnoverResolution(
        amount=span.amount,
        source=TurnoverSource.VAT_FILED if span.is_fully_filed else TurnoverSource.VAT_PENDING,
        vat_work_item_ids=span.vat_work_item_ids,
    )


def vat_turnover_mismatch_expr():
    """The mismatch rule as a SQL predicate on ``AdvancePayment``.

    The row must carry a stored turnover, VAT's coverage rule must be satisfied
    for the period's whole span, and the summed VAT figure must differ from the
    stored one by more than :data:`VAT_TURNOVER_MISMATCH_TOLERANCE`.

    The coverage half comes from VAT; only the tolerance comparison is this
    domain's, because only this domain knows what it stored.
    """
    covering = (
        covering_work_items_select(
            client_record_id=AdvancePayment.client_record_id,
            period=AdvancePayment.period,
            months_count=AdvancePayment.period_months_count,
        )
        .having(
            func.abs(turnover_sum_expr() - AdvancePayment.turnover_amount)
            > VAT_TURNOVER_MISMATCH_TOLERANCE
        )
        .correlate(AdvancePayment)
    )
    return AdvancePayment.turnover_amount.is_not(None) & covering.exists()
