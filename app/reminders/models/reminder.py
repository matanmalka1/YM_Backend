from __future__ import annotations

import datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class ReminderActionType(str, PyEnum):
    CREATE_TASK = "create_task"
    SEND_NOTIFICATION = "send_notification"
    CREATE_TASK_AND_NOTIFY = "create_task_and_notify"


class ReminderStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    FIRED = "fired"
    CANCELED = "canceled"
    FAILED = "failed"


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fire_at: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
    status: Mapped[ReminderStatus] = mapped_column(
        pg_enum(ReminderStatus), default=ReminderStatus.SCHEDULED, index=True
    )
    action_type: Mapped[ReminderActionType] = mapped_column(
        pg_enum(ReminderActionType), nullable=False
    )
    source_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notification_template_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fired_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (Index("idx_reminders_status_fire_at", "status", "fire_at"),)

    def __repr__(self) -> str:
        return (
            f"<Reminder(id={self.id}, action='{self.action_type}', "
            f"status='{self.status}', fire_at='{self.fire_at}')>"
        )
