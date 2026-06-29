from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.enum_utils import pg_enum
from app.utils.time_utils import utcnow


class AuditAction(str, PyEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_ACTIVATED = "user_activated"
    USER_DEACTIVATED = "user_deactivated"
    PASSWORD_RESET = "password_reset"


class AuditStatus(str, PyEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action: Mapped[AuditAction] = mapped_column(pg_enum(AuditAction), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[AuditStatus] = mapped_column(pg_enum(AuditStatus), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # Immutable actor/target name snapshots (§5) so renames don't rewrite admin history.
    actor_display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    target_display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Structured context stored as JSONB on PostgreSQL (JSON on SQLite) — dict, not a string.
    metadata_json: Mapped[Any | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False, index=True)
