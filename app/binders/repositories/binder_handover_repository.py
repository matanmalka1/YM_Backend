from datetime import date

from sqlalchemy import select

from app.binders.models.binder_handover import BinderHandover, BinderHandoverBinder
from app.common.repositories.base_repository import BaseRepository


class BinderHandoverRepository(BaseRepository[BinderHandover]):
    """Data access layer for BinderHandover entities."""

    model = BinderHandover

    def create(
        self,
        client_record_id: int,
        received_by_name: str,
        handed_over_at: date,
        until_period_year: int,
        until_period_month: int,
        binder_ids: list[int],
        created_by: int,
        notes: str | None = None,
    ) -> BinderHandover:
        from app.utils.time_utils import utcnow

        handover = BinderHandover(
            client_record_id=client_record_id,
            received_by_name=received_by_name,
            handed_over_at=handed_over_at,
            until_period_year=until_period_year,
            until_period_month=until_period_month,
            notes=notes,
            created_by=created_by,
            created_at=utcnow(),
        )
        self.db.add(handover)
        self.db.flush()

        for bid in binder_ids:
            assoc = BinderHandoverBinder(handover_id=handover.id, binder_id=bid)
            self.db.add(assoc)
        self.db.flush()

        return handover

    def list_by_client_record(self, client_record_id: int) -> list[BinderHandover]:
        return self.db.scalars(
            select(BinderHandover)
            .where(BinderHandover.client_record_id == client_record_id)
            .order_by(BinderHandover.handed_over_at.desc())
        ).all()

    def get_binder_ids_for_handover(self, handover_id: int) -> list[int]:
        rows = self.db.execute(
            select(BinderHandoverBinder.binder_id).where(
                BinderHandoverBinder.handover_id == handover_id
            )
        ).all()
        return [r.binder_id for r in rows]
