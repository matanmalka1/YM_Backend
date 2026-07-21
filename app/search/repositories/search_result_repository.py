from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.binders.models.binder import Binder
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.repositories.base_repository import BaseRepository
from app.legal_entities.models.legal_entity import LegalEntity


@dataclass(frozen=True)
class ClientMatchRow:
    id: int
    office_client_number: int | None
    name: str
    id_number: str | None
    status: ClientStatus


class SearchResultRepository:
    """Resolves the typed term to the clients it identifies."""

    def __init__(self, db: Session):
        self._db = db

    @staticmethod
    def _term_match(term: str):
        """The term identifies a client by any of its public identifiers.

        A binder number counts as an identifier: it is how the office locates a client
        from physical material, so it resolves to the client that owns the binder. Where
        the binder is now does not change whose it is, so a handed-over binder resolves
        to its owner too — the typed term identifies, it does not filter.
        """
        pattern = f"%{term}%"
        term_binder = aliased(Binder)
        return or_(
            LegalEntity.official_name.ilike(pattern),
            LegalEntity.id_number.ilike(pattern),
            cast(ClientRecord.office_client_number, String).ilike(pattern),
            exists(
                select(term_binder.id).where(
                    term_binder.client_record_id == ClientRecord.id,
                    term_binder.deleted_at.is_(None),
                    term_binder.binder_number.ilike(pattern),
                )
            ),
        )

    def search_clients(
        self, term: str, page: int, page_size: int
    ) -> tuple[list[ClientMatchRow], int]:
        """Clients the term identifies, one row per client."""
        stmt = (
            select(
                ClientRecord.id,
                ClientRecord.office_client_number,
                LegalEntity.official_name.label("name"),
                LegalEntity.id_number,
                ClientRecord.status,
            )
            .select_from(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.deleted_at.is_(None), self._term_match(term.strip()))
            .distinct()
        )

        total = int(self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        stmt = stmt.order_by(LegalEntity.official_name.asc(), ClientRecord.id)
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        return [
            ClientMatchRow(
                id=row.id,
                office_client_number=row.office_client_number,
                name=row.name,
                id_number=row.id_number,
                status=row.status,
            )
            for row in self._db.execute(stmt).all()
        ], total

    def matched_binder_numbers(
        self, client_ids: list[int], term: str | None
    ) -> dict[int, list[str]]:
        """Binder numbers that made each client match, so the row is explainable.

        Mirrors `_term_match` exactly, including handed-over binders: an explanation that
        omits the binder the user typed is worse than none.

        Empty when the term is not a binder number — there is nothing to explain then.
        """
        if not client_ids or not term:
            return {}
        rows = self._db.execute(
            select(Binder.client_record_id, Binder.binder_number)
            .where(
                Binder.client_record_id.in_(client_ids),
                Binder.deleted_at.is_(None),
                Binder.binder_number.ilike(f"%{term.strip()}%"),
            )
            .order_by(Binder.binder_number)
        ).all()
        matches: dict[int, list[str]] = {}
        for client_record_id, binder_number in rows:
            matches.setdefault(client_record_id, []).append(binder_number)
        return matches
