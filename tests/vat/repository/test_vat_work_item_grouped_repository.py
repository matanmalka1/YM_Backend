"""Integration tests for vat_work_item_grouped_repository."""

from datetime import datetime, timezone

from app.common.enums import VatType
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_grouped_repository import (
    list_by_due_date_paginated,
    list_due_date_groups,
)
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _user(db):
    user = User(
        full_name="Grouped Repo Test User",
        email="grouped.repo.test@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def test_grouped_due_date_uses_due_date_effective_not_online_extension(test_db):
    """Group key must equal due_date_effective (statutory), not due_date_effective + 4 days."""
    from datetime import timedelta

    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="Grouped Client", id_number="GC001")

    item = create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-08",
        created_by=user.id,
    )
    test_db.commit()

    groups = list_due_date_groups(test_db)

    assert len(groups) == 1
    group = groups[0]
    assert group["due_date"] == item.due_date_effective
    assert group["due_date"] != item.due_date_effective + timedelta(days=4)


def test_paginated_due_date_count_excludes_soft_deleted_items(test_db):
    user = _user(test_db)
    client = seed_client_identity(
        test_db,
        full_name="Grouped Count Client",
        id_number="GC002",
    )

    item = create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-08",
        created_by=user.id,
    )
    due_date = item.due_date_effective
    item.deleted_at = datetime.now(timezone.utc)
    test_db.commit()

    items, total = list_by_due_date_paginated(test_db, due_date)

    assert items == []
    assert total == 0


# ── New tests for SQL-level aggregation correctness ──────────────────────────


def test_groups_counts_filed_pending_not_filed_overdue(test_db):
    """filed_count, pending_count, not_filed_count, overdue_count are correct.

    Three clients each have one item for the same period so they share
    the same due_date_effective from the calendar — no mutation needed.
    """
    from datetime import date

    user = _user(test_db)
    client_a = seed_client_identity(test_db, full_name="Count Client A", id_number="GC003A")
    client_b = seed_client_identity(test_db, full_name="Count Client B", id_number="GC003B")
    client_c = seed_client_identity(test_db, full_name="Count Client C", id_number="GC003C")

    filed_item = create_linked_vat_work_item(
        test_db,
        client_record_id=client_a.id,
        period="2026-01",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    pending_item = create_linked_vat_work_item(
        test_db,
        client_record_id=client_b.id,
        period="2026-01",
        created_by=user.id,
        status=VatWorkItemStatus.PENDING_MATERIALS,
    )
    data_entry_item = create_linked_vat_work_item(
        test_db,
        client_record_id=client_c.id,
        period="2026-01",
        created_by=user.id,
        status=VatWorkItemStatus.DATA_ENTRY_IN_PROGRESS,
    )
    test_db.commit()

    shared_due = filed_item.due_date_effective
    assert pending_item.due_date_effective == shared_due
    assert data_entry_item.due_date_effective == shared_due

    groups = list_due_date_groups(test_db)
    grp = next(g for g in groups if g["due_date"] == shared_due)

    assert grp["total_count"] == 3
    assert grp["filed_count"] == 1
    assert grp["pending_count"] == 1
    # not_filed = PENDING_MATERIALS + DATA_ENTRY_IN_PROGRESS (FILED is excluded)
    assert grp["not_filed_count"] == 2
    # overdue only if the shared due date is in the past
    expected_overdue = 2 if shared_due < date.today() else 0
    assert grp["overdue_count"] == expected_overdue


def test_groups_excludes_soft_deleted_items(test_db):
    """Soft-deleted VatWorkItems must not appear in group counts."""
    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="Deleted Item Client", id_number="GC004")

    item = create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-07",
        created_by=user.id,
    )
    item.deleted_at = datetime.now(timezone.utc)
    test_db.commit()

    groups = list_due_date_groups(test_db, client_record_ids=[client.id])
    assert groups == []


def test_groups_excludes_soft_deleted_client_records(test_db):
    """VAT items whose ClientRecord is soft-deleted must not appear."""
    from app.clients.models.client_record import ClientRecord
    from sqlalchemy import select

    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="Deleted Client", id_number="GC005")

    create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-08",
        created_by=user.id,
    )
    cr = test_db.scalars(select(ClientRecord).where(ClientRecord.id == client.id)).first()
    cr.deleted_at = datetime.now(timezone.utc)
    test_db.commit()

    groups = list_due_date_groups(test_db, client_record_ids=[client.id])
    assert groups == []


def test_groups_periods_list_is_correct(test_db):
    """periods[] contains all distinct (period, period_type) combos for the due_date.

    Two clients, same period — same due_date from calendar, both periods appear in the list.
    """
    user = _user(test_db)
    client_a = seed_client_identity(test_db, full_name="Periods Client A", id_number="GC006")
    client_b = seed_client_identity(test_db, full_name="Periods Client B", id_number="GC007")

    item_a = create_linked_vat_work_item(
        test_db,
        client_record_id=client_a.id,
        period="2026-09",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    item_b = create_linked_vat_work_item(
        test_db,
        client_record_id=client_b.id,
        period="2026-09",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    test_db.commit()

    shared_due = item_a.due_date_effective
    assert item_b.due_date_effective == shared_due

    groups = list_due_date_groups(test_db)
    grp = next(g for g in groups if g["due_date"] == shared_due)

    # Both items share the same period, so periods[] has exactly one distinct entry
    assert len(grp["periods"]) == 1
    assert grp["periods"][0]["period"] == "2026-09"
    assert grp["total_count"] == 2


def test_groups_sorted_by_due_date(test_db):
    """groups[] is sorted ascending by due_date."""
    user = _user(test_db)
    client_a = seed_client_identity(test_db, full_name="Sort Client A", id_number="GC008")
    client_b = seed_client_identity(test_db, full_name="Sort Client B", id_number="GC009")

    create_linked_vat_work_item(
        test_db, client_record_id=client_a.id, period="2026-11", created_by=user.id
    )
    create_linked_vat_work_item(
        test_db, client_record_id=client_b.id, period="2026-01", created_by=user.id
    )
    test_db.commit()

    groups = list_due_date_groups(test_db)
    due_dates = [g["due_date"] for g in groups]
    assert due_dates == sorted(due_dates)


def test_status_summary_no_filter_returns_correct_counts_without_legal_entity_join(
    test_db,
):
    """count_by_status_summary with no filter must not require LegalEntity join.

    Uses before/after delta to verify the new items are counted regardless of
    other data in the DB.
    """
    from app.vat.repositories.vat_work_item_query_repository import (
        VatWorkItemQueryRepository,
    )

    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="Summary Client", id_number="GC010")
    repo = VatWorkItemQueryRepository(test_db)

    before = repo.count_by_status_summary()

    create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=user.id,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
    )
    create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-02",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    test_db.commit()

    after = repo.count_by_status_summary()

    assert (
        after.get(VatWorkItemStatus.MATERIAL_RECEIVED, 0)
        == before.get(VatWorkItemStatus.MATERIAL_RECEIVED, 0) + 1
    )
    assert after.get(VatWorkItemStatus.FILED, 0) == before.get(VatWorkItemStatus.FILED, 0) + 1


def test_status_summary_client_name_filter_still_works(test_db):
    """count_by_status_summary with client_name must still apply LegalEntity join correctly."""
    from app.vat.repositories.vat_work_item_query_repository import (
        VatWorkItemQueryRepository,
    )

    user = _user(test_db)
    target_client = seed_client_identity(
        test_db, full_name="Target Filter Client", id_number="GC011"
    )
    other_client = seed_client_identity(test_db, full_name="Other Filter Client", id_number="GC012")

    create_linked_vat_work_item(
        test_db,
        client_record_id=target_client.id,
        period="2026-03",
        created_by=user.id,
        status=VatWorkItemStatus.FILED,
    )
    create_linked_vat_work_item(
        test_db,
        client_record_id=other_client.id,
        period="2026-03",
        created_by=user.id,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
    )
    test_db.commit()

    repo = VatWorkItemQueryRepository(test_db)
    counts = repo.count_by_status_summary(client_name="Target Filter Client")

    assert counts.get(VatWorkItemStatus.FILED, 0) >= 1
    assert counts.get(VatWorkItemStatus.MATERIAL_RECEIVED, 0) == 0
