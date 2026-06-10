from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.binders.models.binder_lifecycle_log import BinderLifecycleLog
from app.common.repositories.base_repository import BaseRepository


class BinderLifecycleLogRepository(BaseRepository[BinderLifecycleLog]):
    """Data access layer for BinderLifecycleLog entities."""

    model = BinderLifecycleLog

    def __init__(self, db: Session):
        super().__init__(db)

    def append(
        self,
        binder_id: int,
        field_name: str,
        old_value: str,
        new_value: str,
        changed_by_user_id: int,
        notes: str | None = None,
    ) -> BinderLifecycleLog:
        """Append lifecycle field change log entry."""
        log = BinderLifecycleLog(
            binder_id=binder_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_by_user_id=changed_by_user_id,
            notes=notes,
        )
        self.db.add(log)
        self.db.flush()
        return log

    def list_all_by_binder(self, binder_id: int, limit: int = 500) -> list[BinderLifecycleLog]:
        """All lifecycle logs for a binder in chronological order, bounded by limit."""
        return list(
            self.db.scalars(
                select(BinderLifecycleLog)
                .where(BinderLifecycleLog.binder_id == binder_id)
                .order_by(BinderLifecycleLog.changed_at.asc(), BinderLifecycleLog.id.asc())
                .limit(limit)
            ).all()
        )

    def list_by_binder_page(
        self, binder_id: int, page: int, page_size: int
    ) -> tuple[list[BinderLifecycleLog], int]:
        """Paginated lifecycle logs for a binder."""
        base = select(BinderLifecycleLog).where(BinderLifecycleLog.binder_id == binder_id)
        total: int = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = list(
            self.db.scalars(
                base.order_by(BinderLifecycleLog.changed_at.asc(), BinderLifecycleLog.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def list_recent(self, limit: int = 20) -> list[BinderLifecycleLog]:
        return list(
            self.db.scalars(
                select(BinderLifecycleLog)
                .order_by(BinderLifecycleLog.changed_at.desc(), BinderLifecycleLog.id.desc())
                .limit(limit)
            ).all()
        )
