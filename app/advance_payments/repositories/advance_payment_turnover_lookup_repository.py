"""VAT turnover lookup for advance payment context.

One rule, one implementation: :meth:`TurnoverLookupRepository._resolve` decides
what turnover an advance-payment period can draw from its VAT returns. The three
public methods differ only in how many periods they ask about, never in the rule
they apply.

:func:`vat_turnover_mismatch_expr` is the same rule expressed in SQL, for
filtering a set the server never loads into Python. It lives here so the two
forms are read and changed together.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Integer, cast, func, literal, select
from sqlalchemy.orm import Session

from app.advance_payments.advance_payment_constants import VAT_TURNOVER_MISMATCH_TOLERANCE
from app.advance_payments.models.advance_payment import AdvancePayment, TurnoverSource
from app.common.repositories.base_repository import BaseRepository
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem

# FILED items are settled figures; READY_FOR_REVIEW ones can still change before
# filing, which is why they resolve to a weaker source and never to vat_filed.
_FILED_STATUSES = (VatWorkItemStatus.FILED,)
_UNFILED_STATUSES = (VatWorkItemStatus.READY_FOR_REVIEW,)
_RESOLVABLE_STATUSES = (*_FILED_STATUSES, *_UNFILED_STATUSES)


def _expand_period(period: str, months_count: int) -> list[str]:
    year = int(period[:4])
    month = int(period[5:7])
    result = []
    for offset in range(months_count):
        absolute = year * 12 + month - 1 + offset
        result_year = absolute // 12
        result_month = absolute % 12 + 1
        result.append(f"{result_year}-{result_month:02d}")
    return result


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


class TurnoverLookupRepository(BaseRepository[VatWorkItem]):
    """Resolve advance-payment periods against ``vat_work_items.total_output_net``."""

    def __init__(self, db: Session):
        self.db = db

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve_turnover(
        self,
        client_record_id: int,
        period: str,
        period_months_count: int = 1,
    ) -> TurnoverResolution:
        """Resolve a single period."""
        resolved = self._resolve({client_record_id: [(period, period_months_count)]})
        return resolved[(client_record_id, period)]

    def resolve_turnover_for_client(
        self,
        client_record_id: int,
        periods: list[tuple[str, int]],
    ) -> dict[str, TurnoverResolution]:
        """Resolve many periods for one client, keyed by period."""
        if not periods:
            return {}
        resolved = self._resolve({client_record_id: periods})
        return {period: resolved[(client_record_id, period)] for period, _ in periods}

    def resolve_turnover_for_clients(
        self,
        periods_by_client: dict[int, list[tuple[str, int]]],
    ) -> dict[tuple[int, str], TurnoverResolution]:
        """Resolve many periods across many clients, keyed by (client, period)."""
        return self._resolve(periods_by_client)

    # ── The rule ──────────────────────────────────────────────────────────────

    def _resolve(
        self,
        periods_by_client: dict[int, list[tuple[str, int]]],
    ) -> dict[tuple[int, str], TurnoverResolution]:
        """Resolve every requested period in one query.

        A period resolves only when *every* month it covers has a VAT work item.
        A half-covered bi-monthly period stays unresolved rather than reporting a
        silently halved turnover. The source is ``vat_filed`` only when every
        covered month is filed; one unfiled month among them makes the combined
        figure worth no more than that weakest return, so it resolves to
        ``vat_pending``.
        """
        if not periods_by_client:
            return {}

        wanted_months: set[str] = set()
        for periods in periods_by_client.values():
            for period, months_count in periods:
                wanted_months.update(_expand_period(period, months_count))

        rows = self.db.execute(
            select(
                VatWorkItem.client_record_id,
                VatWorkItem.period,
                VatWorkItem.id,
                VatWorkItem.total_output_net,
                VatWorkItem.status,
            ).where(
                VatWorkItem.client_record_id.in_(periods_by_client),
                VatWorkItem.period.in_(wanted_months),
                VatWorkItem.status.in_(_RESOLVABLE_STATUSES),
                VatWorkItem.deleted_at.is_(None),
            )
        ).all()
        # (client, period) is unique among non-deleted work items, so one row each.
        by_month = {(row.client_record_id, row.period): row for row in rows}

        resolved: dict[tuple[int, str], TurnoverResolution] = {}
        for client_record_id, periods in periods_by_client.items():
            for period, months_count in periods:
                months = _expand_period(period, months_count)
                covering = [
                    by_month[(client_record_id, month)]
                    for month in months
                    if (client_record_id, month) in by_month
                ]
                if len(covering) != len(months):
                    resolved[(client_record_id, period)] = _UNRESOLVED
                    continue
                resolved[(client_record_id, period)] = TurnoverResolution(
                    amount=sum(
                        (Decimal(str(row.total_output_net)) for row in covering), Decimal("0")
                    ),
                    source=(
                        TurnoverSource.VAT_FILED
                        if all(row.status in _FILED_STATUSES for row in covering)
                        else TurnoverSource.VAT_PENDING
                    ),
                    vat_work_item_ids=[row.id for row in covering],
                )
        return resolved


def vat_turnover_mismatch_expr():
    """The mismatch rule as a SQL predicate on ``AdvancePayment``.

    Mirrors :meth:`TurnoverLookupRepository._resolve` plus
    :meth:`VatTurnoverMismatch.from_comparison`: the row must carry a stored
    turnover, *every* month the period covers must have a resolvable VAT work
    item, and the summed VAT figure must differ from the stored one by more than
    :data:`VAT_TURNOVER_MISMATCH_TOLERANCE`.

    A Python-side check cannot back a filter: the overview is server-paginated,
    so the set being narrowed is never all in memory. Change this and
    ``_resolve`` together — a row the list filters in must be a row the detail
    route flags.

    Both months of a bi-monthly period fall in the period's own year
    (bi-monthly periods start on an odd month), so months are compared within
    the year rather than by building an end-period string, which has no
    portable spelling across SQLite and Postgres.
    """
    payment_start_month = cast(func.substr(AdvancePayment.period, 6, 2), Integer)
    vat_month = cast(func.substr(VatWorkItem.period, 6, 2), Integer)
    covering = (
        select(literal(1))
        .select_from(VatWorkItem)
        .where(
            VatWorkItem.client_record_id == AdvancePayment.client_record_id,
            VatWorkItem.deleted_at.is_(None),
            VatWorkItem.status.in_(_RESOLVABLE_STATUSES),
            func.substr(VatWorkItem.period, 1, 4) == func.substr(AdvancePayment.period, 1, 4),
            vat_month >= payment_start_month,
            vat_month <= payment_start_month + AdvancePayment.period_months_count - 1,
        )
        # One group: the WHERE already pins a single client. Grouping is explicit
        # because SQLite rejects a HAVING clause without a GROUP BY.
        .group_by(VatWorkItem.client_record_id)
        .having(
            func.count(VatWorkItem.id) == AdvancePayment.period_months_count,
            func.abs(func.sum(VatWorkItem.total_output_net) - AdvancePayment.turnover_amount)
            > VAT_TURNOVER_MISMATCH_TOLERANCE,
        )
        .correlate(AdvancePayment)
    )
    return AdvancePayment.turnover_amount.is_not(None) & covering.exists()
