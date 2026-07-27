"""Filter coverage for the client-scoped VAT work-items list."""

from datetime import date

from app.common.enums import IdNumberType, VatType
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _client_record(client_factory) -> int:
    return client_factory(
        id_number_type=IdNumberType.INDIVIDUAL,
        create_person=False,
        commit=True,
    ).id


def _item(db, repo, client_record_id, user_id, period, **overrides):
    item = create_linked_vat_work_item(
        db,
        repo=repo,
        client_record_id=client_record_id,
        period=period,
        period_type=VatType.MONTHLY,
        created_by=user_id,
        status=overrides.get("status", VatWorkItemStatus.MATERIAL_RECEIVED),
    )
    if "assigned_to" in overrides:
        item.assigned_to = overrides["assigned_to"]
        db.commit()
        db.refresh(item)
    return item


def test_work_items_filter_by_year(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    in_2026 = _item(test_db, repo, cr, user.id, "2026-01")
    _item(test_db, repo, cr, user.id, "2025-01")

    items = repo.list_by_client_record_paginated(cr, year=2026)
    total = repo.count_by_client_record(cr, year=2026)

    assert total == 1
    assert [i.id for i in items] == [in_2026.id]


def test_work_items_filter_by_period(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    target = _item(test_db, repo, cr, user.id, "2026-02")
    _item(test_db, repo, cr, user.id, "2026-03")

    items = repo.list_by_client_record_paginated(cr, period="2026-02")
    total = repo.count_by_client_record(cr, period="2026-02")

    assert total == 1
    assert [i.id for i in items] == [target.id]


def test_work_items_filter_by_status(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    ready = _item(test_db, repo, cr, user.id, "2026-01", status=VatWorkItemStatus.READY_FOR_REVIEW)
    _item(test_db, repo, cr, user.id, "2026-02", status=VatWorkItemStatus.MATERIAL_RECEIVED)

    items = repo.list_by_client_record_paginated(cr, status=VatWorkItemStatus.READY_FOR_REVIEW)
    total = repo.count_by_client_record(cr, status=VatWorkItemStatus.READY_FOR_REVIEW)

    assert total == 1
    assert [i.id for i in items] == [ready.id]


def test_work_items_filter_by_assigned_to(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    other = user_factory()
    cr = _client_record(client_factory)
    mine = _item(test_db, repo, cr, user.id, "2026-01", assigned_to=user.id)
    _item(test_db, repo, cr, user.id, "2026-02", assigned_to=other.id)

    items = repo.list_by_client_record_paginated(cr, assigned_to=user.id)
    total = repo.count_by_client_record(cr, assigned_to=user.id)

    assert total == 1
    assert [i.id for i in items] == [mine.id]


def test_work_items_filter_by_due_date_range(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    # due_date_effective is derived from the linked tax-calendar entry (kept equal to
    # due_date_original to avoid the override-reason rule). Different periods yield
    # different effective due dates; read them back and bracket the early one.
    early = _item(test_db, repo, cr, user.id, "2026-01")
    late = _item(test_db, repo, cr, user.id, "2026-05")
    assert early.due_date_effective is not None and late.due_date_effective is not None
    assert early.due_date_effective < late.due_date_effective

    midpoint = late.due_date_effective
    items = repo.list_by_client_record_paginated(cr, due_before=midpoint)
    total = repo.count_by_client_record(cr, due_before=midpoint)

    # due_before is inclusive (<=), so the late item (== midpoint) is included too; use a
    # strict upper bound just below it to isolate the early item.
    strict = repo.list_by_client_record_paginated(
        cr, due_before=date.fromordinal(midpoint.toordinal() - 1)
    )
    assert total == 2
    assert {i.id for i in items} == {early.id, late.id}
    assert [i.id for i in strict] == [early.id]


def test_work_items_client_scope_is_strict(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr_a = _client_record(client_factory)
    cr_b = _client_record(client_factory)
    mine = _item(test_db, repo, cr_a, user.id, "2026-01")
    _item(test_db, repo, cr_b, user.id, "2026-01")

    items = repo.list_by_client_record_paginated(cr_a)
    total = repo.count_by_client_record(cr_a)

    assert total == 1
    assert [i.id for i in items] == [mine.id]


def test_work_items_filters_combined_with_and(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    match = _item(test_db, repo, cr, user.id, "2026-04", status=VatWorkItemStatus.READY_FOR_REVIEW)
    # Right year, wrong status.
    _item(test_db, repo, cr, user.id, "2026-05", status=VatWorkItemStatus.MATERIAL_RECEIVED)
    # Wrong year, right status.
    _item(test_db, repo, cr, user.id, "2025-04", status=VatWorkItemStatus.READY_FOR_REVIEW)

    items = repo.list_by_client_record_paginated(
        cr, year=2026, status=VatWorkItemStatus.READY_FOR_REVIEW
    )
    total = repo.count_by_client_record(cr, year=2026, status=VatWorkItemStatus.READY_FOR_REVIEW)

    assert total == 1
    assert [i.id for i in items] == [match.id]


def test_work_items_no_match_returns_empty(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    _item(test_db, repo, cr, user.id, "2026-01")

    items = repo.list_by_client_record_paginated(cr, year=1999)
    total = repo.count_by_client_record(cr, year=1999)

    assert total == 0
    assert items == []


def test_work_items_deterministic_tie_breaker(test_db, user_factory, client_factory):
    repo = VatWorkItemRepository(test_db)
    user = user_factory()
    cr = _client_record(client_factory)
    # Distinct periods → order by period desc; same period not allowed (unique constraint),
    # so verify period desc then id desc holds across periods.
    jan = _item(test_db, repo, cr, user.id, "2026-01")
    mar = _item(test_db, repo, cr, user.id, "2026-03")
    feb = _item(test_db, repo, cr, user.id, "2026-02")

    items = repo.list_by_client_record_paginated(cr)

    assert [i.id for i in items] == [mar.id, feb.id, jan.id]
