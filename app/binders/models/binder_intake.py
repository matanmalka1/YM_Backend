from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.binders.models.binder import Binder
from app.utils.time_utils import utcnow


class BinderIntake(Base):
    """
    Material intake event for a binder.

    Every time a client brings materials to the office, an intake event is recorded.
    Each event can include multiple items of different types
    and for different businesses (BinderIntakeMaterial).
    """

    __tablename__ = "binder_intakes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    binder_id: Mapped[int] = mapped_column(
        ForeignKey("binders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    binder: Mapped[Binder] = relationship("Binder", back_populates="intakes")

    # When the material was received.
    received_at: Mapped[date] = mapped_column(nullable=False)

    # Who received the material at the office.
    received_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # General notes about the event ("arrived with an envelope", "some material is missing").
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    def __repr__(self):
        return (
            f"<BinderIntake(id={self.id}, binder_id={self.binder_id}, "
            f"received_at='{self.received_at}')>"
        )
