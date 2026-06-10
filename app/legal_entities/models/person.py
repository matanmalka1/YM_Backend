from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import IdNumberType
from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class Person(Base):
    """Physical individual who may own or be linked to one or more legal entities."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    full_name: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # Person-valid types only — CORPORATION is rejected by the check constraint below.
    id_number: Mapped[str] = mapped_column(String, nullable=False)
    id_number_type: Mapped[IdNumberType] = mapped_column(pg_enum(IdNumberType), nullable=False)

    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    address_street: Mapped[str | None] = mapped_column(String, nullable=True)
    address_building_number: Mapped[str | None] = mapped_column(String, nullable=True)
    address_apartment: Mapped[str | None] = mapped_column(String, nullable=True)
    address_city: Mapped[str | None] = mapped_column(String, nullable=True)
    address_zip_code: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint(
            "id_number_type IN ('individual', 'passport', 'other')",
            name="ck_persons_id_number_type_not_corporation",
        ),
        UniqueConstraint("id_number_type", "id_number", name="uq_person_identity_id"),
        Index("ix_persons_full_name", "full_name"),
        Index("ix_persons_id_number", "id_number"),
    )

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, full_name='{self.full_name}')>"
