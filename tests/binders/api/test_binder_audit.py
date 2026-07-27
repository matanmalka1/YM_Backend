from datetime import date

from app.audit.audit_constants import (
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ENTITY_BINDER,
)
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.services.binder_lifecycle_service import BinderLifecycleService


def _seed_binder_with_audit(db, binder_factory, user_id: int) -> Binder:
    """Create a binder and drive a real lifecycle transition so its audit rows land in
    EntityAuditLog via the generic writer (no legacy BinderLifecycleLog path)."""
    binder = binder_factory(
        binder_number="BND-H-001",
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    service = BinderLifecycleService(db)
    service.log_initial_state(binder, changed_by_user_id=user_id)
    service.mark_ready_for_handover(binder.id, changed_by_user_id=user_id)
    db.commit()
    return binder


def test_generic_binder_audit_returns_lifecycle_events(
    client, test_db, advisor_headers, test_user, binder_factory
):
    binder = _seed_binder_with_audit(test_db, binder_factory, test_user.id)

    resp = client.get(f"/api/v1/audit/{ENTITY_BINDER}/{binder.id}", headers=advisor_headers)
    assert resp.status_code == 200

    payload = resp.json()
    actions = {item["action"] for item in payload["items"]}
    assert ACTION_BINDER_MARKED_READY_FOR_HANDOVER in actions
    # every lifecycle row carries the indexed client context.
    assert all(
        item["metadata_json"]["client_record_id"] == binder.client_record_id
        for item in payload["items"]
    )
    assert payload["entity_deleted"] is False


def test_generic_binder_audit_readable_by_secretary(
    client, test_db, secretary_headers, test_user, binder_factory
):
    binder = _seed_binder_with_audit(test_db, binder_factory, test_user.id)

    resp = client.get(f"/api/v1/audit/{ENTITY_BINDER}/{binder.id}", headers=secretary_headers)
    assert resp.status_code == 200
    assert resp.json()["items"]


def test_generic_binder_audit_pagination(
    client, test_db, advisor_headers, test_user, binder_factory
):
    binder = _seed_binder_with_audit(test_db, binder_factory, test_user.id)

    resp = client.get(
        f"/api/v1/audit/{ENTITY_BINDER}/{binder.id}",
        params={"page": 1, "page_size": 1},
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert len(payload["items"]) == 1
    assert payload["total"] >= 2


def test_legacy_binder_audit_route_is_removed(
    client, test_db, advisor_headers, test_user, binder_factory
):
    binder = _seed_binder_with_audit(test_db, binder_factory, test_user.id)

    resp = client.get(f"/api/v1/binders/{binder.id}/audit", headers=advisor_headers)
    assert resp.status_code == 404
