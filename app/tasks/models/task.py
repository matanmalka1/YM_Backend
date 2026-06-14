from __future__ import annotations

from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.users.models.user import UserRole
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class TaskStatus(str, PyEnum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"


class TaskPriority(str, PyEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pg_enum uses values_callable so DB stores lowercase values ("open", "done", ...)
    # matching the taskstatus / taskpriority PostgreSQL enum types created in migration 0004_tasks.
    status: Mapped[TaskStatus] = mapped_column(
        pg_enum(TaskStatus, name="taskstatus"), nullable=False, default=TaskStatus.OPEN
    )
    priority: Mapped[TaskPriority] = mapped_column(
        pg_enum(TaskPriority, name="taskpriority"),
        nullable=False,
        default=TaskPriority.NORMAL,
    )
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_role: Mapped[UserRole | None] = mapped_column(
        pg_enum(UserRole, name="userrole", create_type=False), nullable=True
    )
    source_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    client_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_records.id"), nullable=True
    )
    action_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    canceled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_priority", "priority"),
        Index("idx_tasks_due_date", "due_date"),
        Index("idx_tasks_assigned_to_user_id", "assigned_to_user_id"),
        Index("idx_tasks_source", "source_domain", "source_id"),
        Index("idx_tasks_client_record_id", "client_record_id"),
    )
