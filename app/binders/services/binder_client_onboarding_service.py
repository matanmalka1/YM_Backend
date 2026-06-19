import logging

from sqlalchemy.orm import Session

from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.clients.models.client_record import ClientRecord

_log = logging.getLogger(__name__)

_AUTO_BINDER_LIFECYCLE_LOG_NOTES = "קלסר נפתח אוטומטית"


def create_initial_binder(
    db: Session,
    client_record: ClientRecord,
    actor_id: int | None,
) -> None:
    """
    Open a bare placeholder binder when a new client is created.

    Requires office_client_number to be set on the client_record.
    If not set, skips creation with a warning — staff must open the first binder
    manually once the office client number is assigned.

    The binder is created with period_start=None (no material received yet).
    """
    if actor_id is None:
        raise ValueError(f"לא ניתן ליצור קלסר אוטומטי ללקוח {client_record.id}: actor_id חסר")
    if client_record.office_client_number is None:
        raise ValueError(f"לא ניתן ליצור קלסר: מספר לקוח משרד חסר ללקוח {client_record.id}")

    binder_repo = BinderRepository(db)
    seq = binder_repo.count_all_by_client(client_record.id) + 1
    binder = binder_repo.create(
        client_record_id=client_record.id,
        binder_number=f"{client_record.office_client_number}/{seq}",
        period_start=None,
        created_by=actor_id,
    )
    BinderLifecycleService(db).log_initial_state(
        binder=binder,
        changed_by_user_id=actor_id,
        notes=_AUTO_BINDER_LIFECYCLE_LOG_NOTES,
    )
