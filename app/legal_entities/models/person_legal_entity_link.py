from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class PersonLegalEntityRole(str, PyEnum):
    OWNER = "owner"
    AUTHORIZED_SIGNATORY = "authorized_signatory"
    CONTROLLING_SHAREHOLDER = "controlling_shareholder"


class PersonLegalEntityLink(Base):
    """Associates a Person with a LegalEntity and captures the relationship role."""

    __tablename__ = "person_legal_entity_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    legal_entity_id: Mapped[int] = mapped_column(ForeignKey("legal_entities.id"), nullable=False)
    role: Mapped[PersonLegalEntityRole] = mapped_column(
        pg_enum(PersonLegalEntityRole),
        nullable=False,
        default=PersonLegalEntityRole.OWNER,
    )

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    person: Mapped["Person"] = relationship(
        "Person", foreign_keys=[person_id], lazy="select", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint(
            "person_id", "legal_entity_id", "role", name="uq_person_legal_entity_role"
        ),
        Index("ix_person_legal_entity_links_legal_entity_id", "legal_entity_id"),
    )

    def __repr__(self) -> str:
        return f"<PersonLegalEntityLink(person_id={self.person_id}, legal_entity_id={self.legal_entity_id}, role='{self.role}')>"
