from __future__ import annotations

from sqlalchemy import asc, case, desc, func, select
from sqlalchemy.orm import Session

from app.clients.enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import EntityType
from app.common.repositories.base_repository import BaseRepository
from app.core.api_types import SortOrder
from app.core.exceptions import NotFoundError
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)
from app.utils.time_utils import utcnow

OFFICE_CLIENT_NUMBER_START = 100001


class ClientRecordRepository:
    """
    Data access for ClientRecord + LegalEntity.
    """

    def __init__(self, db: Session):
        self.db = db

    # ── write methods ────────────────────────────────────────────────────────

    def create(
        self,
        *,
        legal_entity_id: int,
        accountant_id: int | None = None,
        status: ClientStatus = ClientStatus.ACTIVE,
        notes: str | None = None,
        created_by: int | None = None,
    ) -> ClientRecord:
        record = ClientRecord(
            legal_entity_id=legal_entity_id,
            accountant_id=accountant_id,
            status=status,
            notes=notes,
            created_by=created_by,
        )
        self.db.add(record)
        self.db.flush()
        self.db.refresh(record, ["office_client_number"])
        return record

    def update_status(self, client_record_id: int, status: ClientStatus) -> ClientRecord | None:
        record = self.db.scalars(
            select(ClientRecord).where(
                ClientRecord.id == client_record_id, ClientRecord.deleted_at.is_(None)
            )
        ).first()
        if not record:
            return None
        record.status = status
        self.db.flush()
        return record

    def soft_delete(self, client_record_id: int, deleted_by: int) -> bool:
        record = self.db.scalars(
            select(ClientRecord).where(ClientRecord.id == client_record_id)
        ).first()
        if not record:
            return False
        record.deleted_at = utcnow()
        record.deleted_by = deleted_by
        self.db.flush()
        return True

    def restore(self, client_record_id: int, restored_by: int) -> ClientRecord | None:
        record = self.db.scalars(
            select(ClientRecord).where(ClientRecord.id == client_record_id)
        ).first()
        if not record or record.deleted_at is None:
            return None
        record.deleted_at = None
        record.deleted_by = None
        record.restored_at = utcnow()
        record.restored_by = restored_by
        self.db.flush()
        return record

    # ── single-record lookups ────────────────────────────────────────────────

    def get_by_id(self, client_record_id: int) -> ClientRecord | None:
        return self.db.scalars(
            select(ClientRecord).where(
                ClientRecord.id == client_record_id, ClientRecord.deleted_at.is_(None)
            )
        ).first()

    def get_by_id_including_deleted(self, client_record_id: int) -> ClientRecord | None:
        return self.db.scalars(
            select(ClientRecord).where(ClientRecord.id == client_record_id)
        ).first()

    def get_by_legal_entity_id(self, legal_entity_id: int) -> ClientRecord | None:
        return self.db.scalars(
            select(ClientRecord).where(
                ClientRecord.legal_entity_id == legal_entity_id,
                ClientRecord.deleted_at.is_(None),
            )
        ).first()

    def get_legal_entity_id_by_client_record_id(self, client_record_id: int) -> int:
        """Return legal_entity_id for a ClientRecord, or raise NotFoundError."""
        row = self.db.execute(
            select(ClientRecord.legal_entity_id).where(
                ClientRecord.id == client_record_id, ClientRecord.deleted_at.is_(None)
            )
        ).first()
        if row is None:
            raise NotFoundError(
                f"רשומת לקוח {client_record_id} לא נמצאה",
                "CLIENT_RECORD.NOT_FOUND",
            )
        return row[0]

    # ── active-record lookups by id_number (via LegalEntity JOIN) ────────────

    def get_active_by_id_number(self, id_number: str) -> list[ClientRecord]:
        """Active ClientRecords whose LegalEntity has the given id_number."""
        return self.db.scalars(
            select(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(LegalEntity.id_number == id_number, ClientRecord.deleted_at.is_(None))
        ).all()

    def get_deleted_by_id_number(self, id_number: str) -> list[ClientRecord]:
        """Soft-deleted ClientRecords whose LegalEntity has the given id_number."""
        return self.db.scalars(
            select(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(LegalEntity.id_number == id_number, ClientRecord.deleted_at.isnot(None))
            .order_by(ClientRecord.deleted_at.desc())
        ).all()

    # ── batch lookups ────────────────────────────────────────────────────────

    def list_by_ids(self, client_record_ids: list[int]) -> list[ClientRecord]:
        if not client_record_ids:
            return []
        return self.db.scalars(
            select(ClientRecord).where(
                ClientRecord.id.in_(client_record_ids),
                ClientRecord.deleted_at.is_(None),
            )
        ).all()

    # ── list / count / search (join LegalEntity for name/id_number filters) ──

    _SORTABLE_FIELDS = {
        "official_name": LegalEntity.official_name,
        "created_at": ClientRecord.created_at,
        "status": ClientRecord.status,
    }

    _ENTITY_TYPE_ORDER = ["osek_patur", "osek_murshe", "company_ltd", "employee"]

    def _active_query(self):
        return (
            select(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.deleted_at.is_(None))
        )

    def _apply_list_filters(
        self,
        stmt,
        search=None,
        status=None,
        accountant_id=None,
        entity_type=None,
        client_id=None,
        id_number=None,
    ):
        if client_id is not None:
            stmt = stmt.where(ClientRecord.id == client_id)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                LegalEntity.official_name.ilike(term) | LegalEntity.id_number.ilike(term)
            )
        if id_number:
            stmt = stmt.where(LegalEntity.id_number.ilike(f"%{id_number.strip()}%"))
        if status:
            stmt = stmt.where(ClientRecord.status == status)
        if accountant_id is not None:
            stmt = stmt.where(ClientRecord.accountant_id == accountant_id)
        if entity_type is not None:
            stmt = stmt.where(LegalEntity.entity_type == entity_type)
        return stmt

    def list(
        self,
        search: str | None = None,
        status: ClientStatus | None = None,
        accountant_id: int | None = None,
        entity_type: EntityType | None = None,
        sort_by: str = "official_name",
        order: SortOrder | str = SortOrder.asc,
        page: int = 1,
        page_size: int = 20,
    ) -> list[ClientRecord]:
        stmt = self._apply_list_filters(
            self._active_query(), search, status, accountant_id, entity_type
        )
        if sort_by == "entity_type":
            order_map = {v: i for i, v in enumerate(self._ENTITY_TYPE_ORDER)}
            sort_col = case(order_map, value=LegalEntity.entity_type)
        else:
            sort_col = self._SORTABLE_FIELDS.get(sort_by, LegalEntity.official_name)
        order = SortOrder(order)
        stmt = stmt.order_by(desc(sort_col) if order is SortOrder.desc else asc(sort_col))
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def list_sidebar(
        self,
        search: str | None = None,
        sort_by: str = "full_name",
        order: SortOrder | str = SortOrder.asc,
        page: int = 1,
        page_size: int = 100,
    ):
        full_name = func.coalesce(Person.full_name, LegalEntity.official_name).label("full_name")
        stmt = (
            select(
                ClientRecord.id,
                full_name,
                ClientRecord.office_client_number,
                Person.phone,
                Person.email,
                LegalEntity.entity_type,
                LegalEntity.vat_reporting_frequency,
            )
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .outerjoin(
                PersonLegalEntityLink,
                (PersonLegalEntityLink.legal_entity_id == LegalEntity.id)
                & (PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER),
            )
            .outerjoin(Person, Person.id == PersonLegalEntityLink.person_id)
            .where(ClientRecord.deleted_at.is_(None))
        )
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                full_name.ilike(term)
                | LegalEntity.official_name.ilike(term)
                | LegalEntity.id_number.ilike(term)
            )
        sort_col = (
            ClientRecord.office_client_number if sort_by == "office_client_number" else full_name
        )
        order = SortOrder(order)
        stmt = stmt.order_by(desc(sort_col) if order is SortOrder.desc else asc(sort_col))
        stmt = BaseRepository.apply_pagination(stmt, page, page_size)
        return self.db.execute(stmt).mappings().all()

    def count(
        self,
        search: str | None = None,
        status: ClientStatus | None = None,
        accountant_id: int | None = None,
        entity_type: EntityType | None = None,
    ) -> int:
        count_stmt = self._apply_list_filters(
            select(func.count(ClientRecord.id))
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.deleted_at.is_(None)),
            search,
            status,
            accountant_id,
            entity_type,
        )
        return self.db.scalar(count_stmt)

    def count_sidebar(self, search: str | None = None) -> int:
        full_name_expr = func.coalesce(
            Person.full_name,
            LegalEntity.official_name,
        )
        stmt = (
            select(func.count(ClientRecord.id))
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .outerjoin(
                PersonLegalEntityLink,
                (PersonLegalEntityLink.legal_entity_id == LegalEntity.id)
                & (PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER),
            )
            .outerjoin(Person, Person.id == PersonLegalEntityLink.person_id)
            .where(ClientRecord.deleted_at.is_(None))
        )
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                full_name_expr.ilike(term)
                | LegalEntity.official_name.ilike(term)
                | LegalEntity.id_number.ilike(term)
            )
        return self.db.scalar(stmt)

    def search(
        self,
        search: str | None = None,
        client_id: int | None = None,
        id_number: str | None = None,
        status: ClientStatus | None = None,
        entity_type: EntityType | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ClientRecord], int]:
        """Cross-domain search by name / id_number / status / entity_type."""
        stmt = self._apply_list_filters(
            self._active_query(),
            search=search,
            status=status,
            entity_type=entity_type,
            client_id=client_id,
            id_number=id_number,
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        stmt = BaseRepository.apply_pagination(
            stmt.order_by(LegalEntity.official_name.asc()), page, page_size
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def list_all(self) -> list[ClientRecord]:
        """All active ClientRecords ordered by official_name."""
        return list(
            self.db.scalars(self._active_query().order_by(LegalEntity.official_name.asc())).all()
        )

    def get_signer_name_by_legal_entity_id(self, legal_entity_id: int) -> str | None:
        """Return the display name for signature use: Person.full_name (OWNER) or LegalEntity.official_name."""
        row = self.db.execute(
            select(Person.full_name, LegalEntity.official_name)
            .select_from(LegalEntity)
            .outerjoin(
                PersonLegalEntityLink,
                (PersonLegalEntityLink.legal_entity_id == LegalEntity.id)
                & (PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER),
            )
            .outerjoin(Person, Person.id == PersonLegalEntityLink.person_id)
            .where(LegalEntity.id == legal_entity_id)
            .order_by(PersonLegalEntityLink.id.asc())
        ).first()
        if row is None:
            return None
        person_name, official_name = row
        return person_name or official_name or None

    def count_by_status(
        self,
        search: str | None = None,
        accountant_id: int | None = None,
        entity_type=None,
    ) -> dict[ClientStatus, int]:
        """Active ClientRecords grouped by status, respecting active filters."""
        stmt = self._apply_list_filters(
            select(ClientRecord.status, func.count(ClientRecord.id))
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .where(ClientRecord.deleted_at.is_(None))
            .group_by(ClientRecord.status),
            search=search,
            accountant_id=accountant_id,
            entity_type=entity_type,
        )
        rows = self.db.execute(stmt).all()
        return {status: count for status, count in rows}
