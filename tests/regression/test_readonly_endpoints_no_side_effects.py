from datetime import date, timedelta

from sqlalchemy import func, select

from app.audit.audit_constants import ACTION_BINDER_MATERIAL_RECEIVED, ENTITY_BINDER
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.binders.binder_audit import binder_metadata
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.clients.models.client_record import ClientRecord


def test_readonly_get_endpoints_keep_db_state_intact(
    client, advisor_headers, test_db, test_user, create_client_with_business
):
    today = date.today()
    c, _business = create_client_with_business(
        full_name="Client D",
        id_number="444444444",
    )

    b_open = Binder(
        client_record_id=c.id,
        binder_number="BND-OPEN",
        period_start=today,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
    )
    b_overdue = Binder(
        client_record_id=c.id,
        binder_number="BND-OVERDUE",
        period_start=today - timedelta(days=100),
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
    )
    b_due_today = Binder(
        client_record_id=c.id,
        binder_number="BND-DUE",
        period_start=today,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        created_by=test_user.id,
    )
    test_db.add_all([b_open, b_overdue, b_due_today])
    test_db.commit()

    test_db.refresh(b_open)
    EntityAuditWriter(test_db).record_action(
        ENTITY_BINDER,
        b_open.id,
        test_user.id,
        ACTION_BINDER_MATERIAL_RECEIVED,
        old_value=None,
        new_value={"location_status": BinderLocationStatus.IN_OFFICE.value},
        note="seed",
        actor_display_name=test_user.full_name,
        metadata_json=binder_metadata(b_open),
    )
    test_db.commit()

    baseline = {
        "binders": test_db.scalar(select(func.count(Binder.id))),
        "logs": test_db.scalar(select(func.count(EntityAuditLog.id))),
        "clients": test_db.scalar(select(func.count(ClientRecord.id))),
        "lifecycles": {
            b.id: (b.location_status.value, b.capacity_status.value)
            for b in test_db.scalars(select(Binder)).all()
        },
    }

    r_client_binders = client.get(
        f"/api/v1/binders?client_record_id={c.id}", headers=advisor_headers
    )
    assert r_client_binders.status_code == 200
    assert r_client_binders.json()["total"] == 3

    # Binder lifecycle audit is served by the generic audit route (Phase 5).
    r_audit = client.get(f"/api/v1/audit/binder/{b_open.id}", headers=advisor_headers)
    assert r_audit.status_code == 200
    assert "items" in r_audit.json()

    r_overview = client.get("/api/v1/dashboard/overview", headers=advisor_headers)
    assert r_overview.status_code == 200
    assert "is_empty" in r_overview.json()
    assert "open_charges_count" in r_overview.json()

    assert test_db.scalar(select(func.count(Binder.id))) == baseline["binders"]
    assert test_db.scalar(select(func.count(EntityAuditLog.id))) == baseline["logs"]
    assert test_db.scalar(select(func.count(ClientRecord.id))) == baseline["clients"]
    assert {
        b.id: (b.location_status.value, b.capacity_status.value)
        for b in test_db.scalars(select(Binder)).all()
    } == baseline["lifecycles"]
