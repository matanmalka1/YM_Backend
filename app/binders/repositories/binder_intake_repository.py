from datetime import date

from sqlalchemy import func, select

from app.binders.models.binder_intake import BinderIntake
from app.common.repositories.base_repository import BaseRepository


class BinderIntakeRepository(BaseRepository[BinderIntake]):
    """Data access layer for BinderIntake entities."""

    model = BinderIntake

    def create(
        self,
        binder_id: int,
        received_at: date,
        received_by: int,
        notes: str | None = None,
    ) -> BinderIntake:
        """Create a new intake record for a binder."""
        intake = BinderIntake(
            binder_id=binder_id,
            received_at=received_at,
            received_by=received_by,
            notes=notes,
        )
        self.db.add(intake)
        self.db.flush()
        return intake

    def get_first_by_binder(self, binder_id: int) -> BinderIntake | None:
        """Get the earliest intake for a binder (first material received)."""
        return self.db.scalars(
            select(BinderIntake)
            .where(BinderIntake.binder_id == binder_id)
            .order_by(BinderIntake.received_at.asc())
        ).first()

    def list_by_binder_page(
        self, binder_id: int, page: int, page_size: int
    ) -> tuple[list[BinderIntake], int]:
        """Paginated intakes for a binder."""
        base = select(BinderIntake).where(BinderIntake.binder_id == binder_id)
        total: int = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = self.apply_pagination(base.order_by(BinderIntake.received_at.asc()), page, page_size)
        items = list(self.db.scalars(stmt).all())
        return items, total
