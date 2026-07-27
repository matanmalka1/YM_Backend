from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class IdempotencyStatus(str, PyEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), nullable=False)
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(pg_enum(IdempotencyStatus), nullable=False)
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    response_body: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (PrimaryKeyConstraint("key", "route", "user_id", name="pk_idempotency_keys"),)
