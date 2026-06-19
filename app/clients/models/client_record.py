from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Sequence, Text, column, event, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

from app.clients.client_enums import ClientStatus
from app.common.soft_delete import SoftDeletableMixin
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow

# No metadata= so create_all never emits CREATE SEQUENCE; Alembic migration 0001 handles that.
office_client_number_seq = Sequence("client_office_number_seq", start=100001)


class ClientRecord(SoftDeletableMixin, Base):
    """Office CRM record and workflow anchor — one active record per legal entity."""

    __tablename__ = "client_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    legal_entity_id: Mapped[int] = mapped_column(
        ForeignKey("legal_entities.id"), nullable=False, index=True
    )

    office_client_number: Mapped[int] = mapped_column(nullable=False)
    accountant_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[ClientStatus] = mapped_column(
        pg_enum(ClientStatus), nullable=False, default=ClientStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    __table_args__ = (
        # One active ClientRecord per LegalEntity (soft-delete aware)
        Index(
            "ix_client_records_legal_entity_id_active",
            "legal_entity_id",
            unique=True,
            postgresql_where=column("deleted_at").is_(None),
            sqlite_where=column("deleted_at").is_(None),
        ),
        Index(
            "ix_client_records_office_client_number_active",
            "office_client_number",
            unique=True,
            postgresql_where=column("deleted_at").is_(None),
            sqlite_where=column("deleted_at").is_(None),
        ),
        Index(
            "ix_client_records_active_created_desc",
            text("created_at DESC"),
            postgresql_where=column("deleted_at").is_(None),
            sqlite_where=column("deleted_at").is_(None),
        ),
    )

    def __repr__(self) -> str:
        return f"<ClientRecord(id={self.id}, legal_entity_id={self.legal_entity_id}, status='{self.status}')>"


@event.listens_for(ClientRecord, "before_insert")
def _assign_test_office_client_number(_mapper, connection, target: ClientRecord) -> None:
    if target.office_client_number is not None:
        return

    if connection.dialect.name == "postgresql":
        target.office_client_number = connection.scalar(
            text("SELECT nextval('client_office_number_seq')")
        )
    else:
        current_max = connection.scalar(
            select(func.max(ClientRecord.office_client_number)).select_from(ClientRecord.__table__)
        )
        target.office_client_number = (current_max or 100000) + 1
