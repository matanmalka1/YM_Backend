from datetime import date

import pytest
from sqlalchemy import update

from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.binders.services.binder_intake_service import BinderIntakeService
from app.businesses.models.business import Business, BusinessStatus
from app.core.exceptions import AppError


def _business(
    business_factory, legal_entity_id: int, status: BusinessStatus = BusinessStatus.ACTIVE
) -> Business:
    return business_factory(
        legal_entity_id=legal_entity_id,
        business_name=f"Business {legal_entity_id}",
        status=status,
        opened_at=date.today(),
        commit=True,
    )


def _materials(year: int = 2026, month: int = 2) -> list[dict]:
    return [
        {
            "material_type": "other",
            "period_year": year,
            "period_month_start": month,
            "period_month_end": month,
            "description": "test material",
        }
    ]


def test_receive_creates_composite_binder_label(
    test_db, test_user, business_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-NEW-001",
        id_number="BI-SVC-NEW-001",
        office_client_number=100301,
    )
    _business(business_factory, client.legal_entity_id)

    service = BinderIntakeService(test_db)
    binder, _, is_new = service.receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=_materials(),
    )

    assert is_new is True
    assert binder.binder_number == "100301/1"
    assert binder.period_start == date(2026, 2, 1)


def test_receive_reuses_existing_binder_for_same_client(
    test_db, test_user, business_factory, binder_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-003",
        id_number="BI-SVC-003",
        office_client_number=100302,
    )
    _business(business_factory, client.legal_entity_id)
    existing = binder_factory(
        client_record_id=client.id,
        binder_number="100302/1",
        period_start=date.today(),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    service = BinderIntakeService(test_db)
    binder, intake, is_new = service.receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        notes="existing binder path",
        materials=_materials(),
    )

    assert binder.id == existing.id
    assert intake.binder_id == existing.id
    assert is_new is False


def test_receive_backfills_period_start_for_existing_binder_without_period(
    test_db, test_user, business_factory, binder_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-BACKFILL-001",
        id_number="BI-SVC-BACKFILL-001",
        office_client_number=100307,
    )
    _business(business_factory, client.legal_entity_id)
    existing = binder_factory(
        client_record_id=client.id,
        binder_number="100307/1",
        period_start=None,
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    service = BinderIntakeService(test_db)
    binder, intake, is_new = service.receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        notes="backfill period start",
        materials=_materials(year=2026, month=4),
    )

    assert binder.id == existing.id
    assert intake.binder_id == existing.id
    assert is_new is False
    assert binder.period_start == date(2026, 4, 1)


def test_receive_raises_when_all_businesses_locked(
    test_db, test_user, business_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-LOCKED-001",
        id_number="BI-SVC-LOCKED-001",
        office_client_number=100303,
    )
    _business(business_factory, client.legal_entity_id)
    test_db.execute(
        update(Business)
        .where(Business.legal_entity_id == client.legal_entity_id)
        .values(status=BusinessStatus.FROZEN)
    )
    test_db.commit()

    service = BinderIntakeService(test_db)
    with pytest.raises(AppError) as exc_info:
        service.receive(
            client_record_id=client.id,
            received_at=date.today(),
            received_by=test_user.id,
            materials=_materials(),
        )

    assert exc_info.value.code == "BINDER.CLIENT_LOCKED"


def test_receive_second_binder_increments_seq_after_full_binder(
    test_db, test_user, business_factory, binder_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-SEQ-001",
        id_number="BI-SVC-SEQ-001",
        office_client_number=100304,
    )
    _business(business_factory, client.legal_entity_id)

    binder_factory(
        client_record_id=client.id,
        binder_number="100304/1",
        period_start=date.today(),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.FULL,
        commit=True,
    )

    service = BinderIntakeService(test_db)
    binder, _, is_new = service.receive(
        client_record_id=client.id,
        received_at=date.today(),
        received_by=test_user.id,
        materials=_materials(month=3),
    )

    assert is_new is True
    assert binder.binder_number == "100304/2"
    assert binder.period_start == date(2026, 3, 1)


def test_receive_old_period_prefers_matching_in_office_full_binder(
    test_db, test_user, business_factory, binder_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-OLD-001",
        id_number="BI-SVC-OLD-001",
        office_client_number=100305,
    )
    _business(business_factory, client.legal_entity_id)

    old_binder = binder_factory(
        client_record_id=client.id,
        binder_number="100305/1",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 28),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.FULL,
        commit=True,
    )
    active_binder = binder_factory(
        client_record_id=client.id,
        binder_number="100305/2",
        period_start=date(2026, 3, 1),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    service = BinderIntakeService(test_db)
    binder, intake, is_new = service.receive(
        client_record_id=client.id,
        received_at=date(2026, 4, 5),
        received_by=test_user.id,
        open_new_binder=True,
        materials=_materials(year=2026, month=2),
    )

    assert is_new is False
    assert binder.id == old_binder.id
    assert intake.binder_id == old_binder.id
    assert test_db.get(Binder, active_binder.id).location_status == BinderLocationStatus.IN_OFFICE


def test_receive_old_period_falls_back_to_active_binder_with_note(
    test_db, test_user, business_factory, binder_factory, client_factory
):
    client = client_factory(
        full_name="Binder Intake BI-SVC-OLD-002",
        id_number="BI-SVC-OLD-002",
        office_client_number=100306,
    )
    _business(business_factory, client.legal_entity_id)

    binder_factory(
        client_record_id=client.id,
        binder_number="100306/1",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.FULL,
        commit=True,
    )
    active_binder = binder_factory(
        client_record_id=client.id,
        binder_number="100306/2",
        period_start=date(2026, 3, 1),
        created_by=test_user.id,
        location_status=BinderLocationStatus.IN_OFFICE,
        capacity_status=BinderCapacityStatus.OPEN,
        commit=True,
    )

    service = BinderIntakeService(test_db)
    binder, intake, is_new = service.receive(
        client_record_id=client.id,
        received_at=date(2026, 4, 5),
        received_by=test_user.id,
        open_new_binder=True,
        notes="old-period material arrived after the binder was already closed",
        materials=_materials(year=2026, month=2),
    )

    assert is_new is False
    assert binder.id == active_binder.id
    assert intake.binder_id == active_binder.id
    refreshed_active = test_db.get(Binder, active_binder.id)
    assert refreshed_active.location_status == BinderLocationStatus.IN_OFFICE
    assert refreshed_active.period_end is None
