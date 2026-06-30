from datetime import date

from app.binders.repositories.binder_repository import BinderRepository
from app.binders.services.binder_lifecycle_service import BinderLifecycleService
from app.timeline.services.timeline_service import TimelineService
from tests.helpers.identity import seed_client_identity


def _binder(db, client_id: int, user_id: int):
    return BinderRepository(db).create(
        client_record_id=client_id,
        binder_number="TL-1",
        period_start=date(2026, 1, 1),
        created_by=user_id,
    )


def test_binder_lifecycle_events_sourced_from_entity_audit_log(test_db, test_user):
    """Timeline binder lifecycle events are now read from EntityAuditLog binder.* rows,
    not the legacy BinderLifecycleLog table."""
    client = seed_client_identity(test_db, full_name="Timeline Binder", id_number="TL-100")
    binder = _binder(test_db, client.id, test_user.id)

    lifecycle = BinderLifecycleService(test_db)
    lifecycle.mark_full(binder.id, changed_by_user_id=test_user.id)
    lifecycle.mark_ready_for_handover(binder.id, changed_by_user_id=test_user.id)
    test_db.flush()

    events, _total = TimelineService(test_db).get_client_timeline(client.id)
    lifecycle_events = [e for e in events if e["event_type"] == "binder_lifecycle_change"]

    # mark_full + mark_ready_for_handover each surface one lifecycle-change event.
    new_values = {e["metadata"]["new_value"] for e in lifecycle_events}
    assert "full" in new_values
    assert "ready_for_handover" in new_values
    # binder.created (null->in_office initial) is NOT a lifecycle-change event — the
    # live binder_received builder covers reception.
    assert all(e["metadata"]["new_value"] != "in_office" for e in lifecycle_events)
