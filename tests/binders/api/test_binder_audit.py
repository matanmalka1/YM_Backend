from datetime import date

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.repositories.binder_lifecycle_log_repository import (
    BinderLifecycleLogRepository,
)
from tests.helpers.identity import seed_client_identity


def _seed_binder_with_audit(db, user_id: int):
    client = seed_client_identity(
        db,
        full_name="Audit Client",
        id_number="BND-HIST-1",
    )

    binder = Binder(
        client_record_id=client.id,
        binder_number="BND-H-001",
        period_start=date.today(),
        created_by=user_id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
    )
    db.add(binder)
    db.commit()
    db.refresh(binder)

    log_repo = BinderLifecycleLogRepository(db)
    log_repo.append(
        binder.id,
        field_name="location_status",
        old_value="null",
        new_value="in_office",
        changed_by_user_id=user_id,
    )
    log_repo.append(
        binder.id,
        field_name="location_status",
        old_value="in_office",
        new_value="ready_for_handover",
        changed_by_user_id=user_id,
    )
    return binder


def test_binder_audit_endpoint_returns_logs(client, test_db, advisor_headers, test_user):
    binder = _seed_binder_with_audit(test_db, test_user.id)

    resp = client.get(f"/api/v1/binders/{binder.id}/audit", headers=advisor_headers)
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["binder_id"] == binder.id
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    audit = payload["audit"]
    assert len(audit) == 2
    assert audit[0]["old_value"] == "null"
    assert audit[0]["new_value"] == "in_office"
    assert audit[1]["new_value"] == "ready_for_handover"


def test_binder_audit_pagination(client, test_db, advisor_headers, test_user):
    binder = _seed_binder_with_audit(test_db, test_user.id)

    resp = client.get(
        f"/api/v1/binders/{binder.id}/audit",
        params={"page": 1, "page_size": 1},
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert len(payload["audit"]) == 1

    resp2 = client.get(
        f"/api/v1/binders/{binder.id}/audit",
        params={"page": 2, "page_size": 1},
        headers=advisor_headers,
    )
    assert resp2.status_code == 200
    assert len(resp2.json()["audit"]) == 1


def test_binder_audit_page_size_cap(client, test_db, advisor_headers, test_user):
    binder = _seed_binder_with_audit(test_db, test_user.id)
    resp = client.get(
        f"/api/v1/binders/{binder.id}/audit",
        params={"page_size": 999},
        headers=advisor_headers,
    )
    assert resp.status_code == 422


def test_binder_audit_404_when_missing(client, advisor_headers):
    resp = client.get("/api/v1/binders/9999/audit", headers=advisor_headers)
    assert resp.status_code == 404


def test_binder_history_endpoint_is_removed(client, test_db, advisor_headers, test_user):
    binder = _seed_binder_with_audit(test_db, test_user.id)

    resp = client.get(f"/api/v1/binders/{binder.id}/history", headers=advisor_headers)

    assert resp.status_code == 404
