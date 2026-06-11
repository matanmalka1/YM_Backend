from datetime import date, timedelta

from sqlalchemy import func, select

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.models.binder_lifecycle_log import BinderLifecycleLog
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
    log = BinderLifecycleLog(
        binder_id=b_open.id,
        field_name="location_status",
        old_value="null",
        new_value="in_office",
        changed_by_user_id=test_user.id,
        notes="seed",
    )
    test_db.add(log)
    test_db.commit()

    baseline = {
        "binders": test_db.scalar(select(func.count(Binder.id))),
        "logs": test_db.scalar(select(func.count(BinderLifecycleLog.id))),
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

    r_audit = client.get(f"/api/v1/binders/{b_open.id}/audit", headers=advisor_headers)
    assert r_audit.status_code == 200
    assert r_audit.json()["binder_id"] == b_open.id

    r_overview = client.get("/api/v1/dashboard/overview", headers=advisor_headers)
    assert r_overview.status_code == 200
    assert "is_empty" in r_overview.json()
    assert "open_charges_count" in r_overview.json()

    assert test_db.scalar(select(func.count(Binder.id))) == baseline["binders"]
    assert test_db.scalar(select(func.count(BinderLifecycleLog.id))) == baseline["logs"]
    assert test_db.scalar(select(func.count(ClientRecord.id))) == baseline["clients"]
    assert {
        b.id: (b.location_status.value, b.capacity_status.value)
        for b in test_db.scalars(select(Binder)).all()
    } == baseline["lifecycles"]
