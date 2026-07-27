"""Client-eligibility queries for office-wide advance-payment generation.

Separate from ``AdvancePaymentRepository`` because these read ``ClientRecord``
and ``LegalEntity``, not ``AdvancePayment``: they answer *who* a schedule can be
generated for, before any payment row exists.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.clients.repositories.client_active_scope import (
    eligible_client_status_expr,
    scope_to_active_clients_stmt,
)
from app.legal_entities.models.legal_entity import LegalEntity


def _generation_scope_stmt(stmt):
    """The canonical active-client scope, narrowed to clients we may generate for.

    Soft-delete scoping and the legal-entity join are the shared helper's job. The
    eligibility predicate is the SQL twin of ``assert_client_record_is_active`` —
    ineligible clients are excluded here rather than skipped later, because that
    guard forbids creating an advance for them and a bulk run must never reach
    them. This used to inline its own ``status == ACTIVE``, a fourth copy of the
    rule.
    """
    return scope_to_active_clients_stmt(stmt, ClientRecord, join_legal_entity=True).where(
        eligible_client_status_expr()
    )


class AdvancePaymentGenerationRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_eligible_clients(self) -> int:
        stmt = _generation_scope_stmt(select(func.count(ClientRecord.id))).where(
            LegalEntity.advance_payment_frequency.is_not(None)
        )
        return self.db.scalar(stmt) or 0

    def list_eligible_client_ids(self, *, after_id: int | None, limit: int) -> list[int]:
        """One chunk of eligible client ids, ordered by id.

        Keyset pagination on the primary key, not offset: a run spans several
        requests, and an offset would skip or repeat clients if the eligible set
        changed underneath it.
        """
        stmt = _generation_scope_stmt(select(ClientRecord.id)).where(
            LegalEntity.advance_payment_frequency.is_not(None)
        )
        if after_id is not None:
            stmt = stmt.where(ClientRecord.id > after_id)
        return list(self.db.scalars(stmt.order_by(ClientRecord.id.asc()).limit(limit)))

    def list_clients_without_frequency(self) -> list[tuple[int, str]]:
        """Active clients that have no advance-payment frequency configured.

        Reported rather than silently filtered out: unlike a closed client or an
        already-generated period, a missing frequency is a data gap that leaves
        the client with no schedule at all, and the advisor has to fix it.
        """
        stmt = _generation_scope_stmt(select(ClientRecord.id, LegalEntity.official_name)).where(
            LegalEntity.advance_payment_frequency.is_(None)
        )
        return [
            (row.id, row.official_name)
            for row in self.db.execute(stmt.order_by(LegalEntity.official_name.asc()))
        ]

    def get_client_names(self, client_record_ids: list[int]) -> dict[int, str]:
        if not client_record_ids:
            return {}
        stmt = (
            select(ClientRecord.id, LegalEntity.official_name)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.id.in_(client_record_ids))
        )
        return {row.id: row.official_name for row in self.db.execute(stmt)}
