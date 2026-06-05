from datetime import date, timedelta

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.charge.models.charge import Charge, ChargeStatus, ChargeType
from app.clients.models.client_record import ClientRecord
from app.reminders.models.reminder import Reminder, ReminderActionType, ReminderStatus
from app.tasks.models.task import Task, TaskPriority, TaskStatus
from app.utils.time_utils import utcnow
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.services.actions import source_actions
from app.work_queue.services.common import normalize_source_domain, source_route
from app.work_queue.services.work_queue_service import WorkQueueService
from tests.helpers.task_helpers import create_business
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_unpaid_charge_item_after_threshold(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    unpaid = [i for i in items if i.source_type == WorkQueueSourceType.CHARGE]

    assert len(unpaid) == 1
    assert unpaid[0].source_id == charge.id
    assert unpaid[0].urgency == WorkQueueUrgency.OVERDUE


def test_unpaid_charge_before_threshold_excluded(test_db):
    biz = create_business(test_db)
    test_db.add(
        Charge(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=200,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=10),
        )
    )
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)

    assert [i for i in items if i.source_type == WorkQueueSourceType.CHARGE] == []


def test_work_queue_excludes_reminders(test_db):
    biz = create_business(test_db)
    test_db.add(
        Reminder(
            fire_at=utcnow(),
            action_type=ReminderActionType.SEND_NOTIFICATION,
            status=ReminderStatus.SCHEDULED,
            source_domain="client_record",
            source_id=biz.client_id,
        )
    )
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)

    assert items == []


def test_work_queue_advance_payment_includes_source_payload(test_db):
    biz = create_business(test_db)
    client_record = test_db.get(ClientRecord, biz.client_id)
    client_record.office_client_number = 100001
    due_date = date.today() - timedelta(days=1)
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=biz.client_id,
        period="2026-02",
        due_date=due_date,
        expected_amount=1000,
        paid_amount=250,
    )
    payment.status = AdvancePaymentStatus.PARTIAL
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    item = next(i for i in items if i.source_type == WorkQueueSourceType.ADVANCE_PAYMENT)

    assert item.client_name.startswith("Task Test Client")
    assert item.office_client_number == 100001
    assert item.metadata == {
        "period": "2026-02",
        "period_label": "פברואר 2026",
        "period_months_count": 1,
        "frequency": "monthly",
        "due_date": due_date.isoformat(),
        "status": "partial",
        "expected_amount": "1000.00",
        "paid_amount": "250.00",
        "remaining_amount": "750.00",
        "payment_method": None,
        "paid_at": None,
        "annual_report_id": None,
    }


def test_work_queue_advance_payment_payload_formats_bimonthly_period(test_db):
    biz = create_business(test_db)
    due_date = date.today() + timedelta(days=3)
    create_linked_advance_payment(
        test_db,
        client_record_id=biz.client_id,
        period="2026-03",
        period_months_count=2,
        due_date=due_date,
        expected_amount=1000,
        paid_amount=0,
    )
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    item = next(i for i in items if i.source_type == WorkQueueSourceType.ADVANCE_PAYMENT)

    assert item.metadata["period_label"] == "מרץ–אפריל 2026"
    assert item.metadata["frequency"] == "bimonthly"


def test_work_queue_advance_payment_batch_loads_all_client_identities(test_db):
    first = create_business(test_db)
    second = create_business(test_db)
    test_db.get(ClientRecord, first.client_id).office_client_number = 100001
    test_db.get(ClientRecord, second.client_id).office_client_number = 100003
    due_date = date.today() + timedelta(days=3)
    create_linked_advance_payment(
        test_db,
        client_record_id=first.client_id,
        period="2026-04",
        period_months_count=1,
        due_date=due_date,
        expected_amount=1000,
        paid_amount=0,
    )
    create_linked_advance_payment(
        test_db,
        client_record_id=second.client_id,
        period="2026-03",
        period_months_count=2,
        due_date=due_date,
        expected_amount=1000,
        paid_amount=0,
    )
    test_db.commit()

    items = [
        item
        for item in WorkQueueService(test_db).list_items()
        if item.source_type == WorkQueueSourceType.ADVANCE_PAYMENT
    ]

    identities = {
        item.client_record_id: (item.client_name, item.office_client_number) for item in items
    }
    assert identities[first.client_id][0].startswith("Task Test Client")
    assert identities[first.client_id][1] == 100001
    assert identities[second.client_id][0].startswith("Task Test Client")
    assert identities[second.client_id][1] == 100003


def test_work_queue_batch_loads_charge_client_identities_once(test_db, monkeypatch):
    first = create_business(test_db)
    second = create_business(test_db)
    _add_overdue_charge(test_db, first)
    _add_overdue_charge(test_db, second)
    calls = []

    from app.work_queue.services import common

    original = common.load_client_profiles

    def wrapped(db, client_record_ids):
        ids = list(client_record_ids)
        calls.append(ids)
        return original(db, ids)

    monkeypatch.setattr(common, "load_client_profiles", wrapped)

    items = WorkQueueService(test_db).list_items(
        exclude_source_types=[
            WorkQueueSourceType.VAT_WORK_ITEM,
            WorkQueueSourceType.ANNUAL_REPORT,
            WorkQueueSourceType.ADVANCE_PAYMENT,
            WorkQueueSourceType.BINDER,
        ]
    )

    charge_items = [i for i in items if i.source_type == WorkQueueSourceType.CHARGE]
    assert len(charge_items) == 2
    assert len(calls) == 1
    assert set(calls[0]) == {first.client_id, second.client_id}


def test_work_queue_excludes_requested_source_types(test_db, monkeypatch):
    service = WorkQueueService(test_db)

    def excluded_builder(*args):
        raise AssertionError("excluded builder called")

    monkeypatch.setattr(
        "app.work_queue.services.work_queue_service.vat_work_item_items",
        excluded_builder,
    )
    monkeypatch.setattr(
        "app.work_queue.services.work_queue_service.annual_report_items",
        excluded_builder,
    )
    monkeypatch.setattr(
        "app.work_queue.services.work_queue_service.advance_payment_items",
        excluded_builder,
    )
    monkeypatch.setattr(
        "app.work_queue.services.work_queue_service.charge_items",
        excluded_builder,
    )

    items = service.list_items(exclude_source_types=list(WorkQueueSourceType))

    assert items == []


def test_work_queue_item_can_be_unscoped_to_client():
    item = WorkQueueItem(
        id="vat_work_item:1",
        source_type=WorkQueueSourceType.VAT_WORK_ITEM,
        source_id=1,
        title='מע"מ לא הוגש: אפריל 2026',
        due_date=date.today(),
        urgency=WorkQueueUrgency.APPROACHING,
    )

    assert item.client_record_id is None


def test_work_queue_source_type_contract_has_no_legacy_aliases():
    assert {source_type.value for source_type in WorkQueueSourceType} == {
        "vat_work_item",
        "annual_report",
        "advance_payment",
        "charge",
        "binder",
        "task",
    }
    assert normalize_source_domain("vat_filing") is None
    assert normalize_source_domain("unpaid_charge") is None
    assert normalize_source_domain("stale_binder") is None


def test_system_source_actions_expose_only_safe_link_or_modal_actions():
    for source_type in [
        WorkQueueSourceType.VAT_WORK_ITEM,
        WorkQueueSourceType.ANNUAL_REPORT,
        WorkQueueSourceType.ADVANCE_PAYMENT,
        WorkQueueSourceType.CHARGE,
        WorkQueueSourceType.BINDER,
    ]:
        actions = source_actions(source_type, 1)
        assert actions
        assert all(action.type in {"link", "modal"} for action in actions)
        assert all(action.type != "mutation" for action in actions)
        assert any(action.key == "create_linked_task" for action in actions)


def test_source_routes_only_return_existing_frontend_targets():
    assert source_route(WorkQueueSourceType.VAT_WORK_ITEM, 11) == "/tax/vat/11"
    assert source_route(WorkQueueSourceType.ANNUAL_REPORT, 22) == "/tax/reports/22"
    assert source_route(WorkQueueSourceType.CHARGE, 33) == "/charges?charge_id=33"
    assert source_route(WorkQueueSourceType.BINDER, 44) == "/binders?binder_id=44"
    assert source_route(WorkQueueSourceType.ADVANCE_PAYMENT, 55) == "/tax/advance-payments"


# ── Pagination ────────────────────────────────────────────────────────────────


def test_work_queue_pagination_limit(test_db):
    biz = create_business(test_db)
    for days_ago in [31, 32, 33]:
        test_db.add(
            Charge(
                client_record_id=biz.client_id,
                business_id=biz.id,
                amount=100,
                charge_type=ChargeType.OTHER,
                status=ChargeStatus.ISSUED,
                issued_at=date.today() - timedelta(days=days_ago),
            )
        )
    test_db.commit()

    page1 = WorkQueueService(test_db).list_items(client_record_id=biz.client_id, limit=2, offset=0)
    page2 = WorkQueueService(test_db).list_items(client_record_id=biz.client_id, limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 1
    assert {i.source_id for i in page1}.isdisjoint({i.source_id for i in page2})


def test_work_queue_pagination_offset_beyond_end(test_db):
    biz = create_business(test_db)
    test_db.add(
        Charge(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=100,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=31),
        )
    )
    test_db.commit()

    items = WorkQueueService(test_db).list_items(
        client_record_id=biz.client_id, limit=50, offset=999
    )
    assert items == []


# ── business_id filter semantics ──────────────────────────────────────────────


def test_work_queue_advance_payment_uses_effective_due_date_when_set(test_db):
    """When due_date_effective is set, queue item due_date and metadata must use it, not due_date."""
    biz = create_business(test_db)
    original_due = date.today() - timedelta(days=10)
    effective_due = date.today() + timedelta(days=5)
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=biz.client_id,
        period="2026-01",
        due_date=original_due,
        expected_amount=500,
        paid_amount=0,
    )
    payment.due_date_effective = effective_due
    payment.due_date_override_reason = "הארכה לצורך בדיקה"
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    item = next(i for i in items if i.source_type == WorkQueueSourceType.ADVANCE_PAYMENT)

    assert item.due_date == effective_due
    assert item.metadata["due_date"] == effective_due.isoformat()


def test_business_id_filter_merges_linked_tasks_into_charge_rows(test_db):
    """Tasks linked to a charge must be merged when filtering by business_id."""
    biz = create_business(test_db)
    charge = _add_overdue_charge(test_db, biz)
    task = _add_task_for_source(test_db, source_domain="charge", source_id=charge.id)

    items = WorkQueueService(test_db).list_items(business_id=biz.id)
    charge_rows = [i for i in items if i.source_type == WorkQueueSourceType.CHARGE]

    assert len(charge_rows) == 1
    assert charge_rows[0].linked_tasks_count == 1
    assert charge_rows[0].linked_tasks[0].id == task.id
    assert not any(i.source_type == WorkQueueSourceType.TASK for i in items)


def test_business_id_filter_excludes_standalone_task_rows(test_db):
    """Standalone tasks (no source or unrelated source) must not appear in business-scoped queue."""
    biz = create_business(test_db)
    _add_overdue_charge(test_db, biz)
    _add_task_for_source(test_db, source_domain=None, source_id=None, title="Unrelated manual task")

    items = WorkQueueService(test_db).list_items(business_id=biz.id)

    assert not any(i.source_type == WorkQueueSourceType.TASK for i in items)


def test_business_id_filter_hides_client_level_sources(test_db):
    """When business_id is set, VAT/annual/advance sources must not appear."""
    biz = create_business(test_db)
    due_date = date.today() - timedelta(days=1)
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=biz.client_id,
        period="2026-03",
        due_date=due_date,
        expected_amount=500,
        paid_amount=0,
    )
    payment.status = AdvancePaymentStatus.PENDING
    test_db.commit()

    items = WorkQueueService(test_db).list_items(business_id=biz.id)
    source_types = {i.source_type for i in items}

    assert WorkQueueSourceType.ADVANCE_PAYMENT not in source_types
    assert WorkQueueSourceType.VAT_WORK_ITEM not in source_types
    assert WorkQueueSourceType.ANNUAL_REPORT not in source_types


def test_business_id_filter_returns_unpaid_charge_for_that_business(test_db):
    biz = create_business(test_db)
    other_biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=750,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    other_charge = Charge(
        client_record_id=other_biz.client_id,
        business_id=other_biz.id,
        amount=200,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add_all([charge, other_charge])
    test_db.commit()

    items = WorkQueueService(test_db).list_items(business_id=biz.id)
    unpaid = [i for i in items if i.source_type == WorkQueueSourceType.CHARGE]

    assert len(unpaid) == 1
    assert unpaid[0].source_id == charge.id


# ── Charge urgency is always OVERDUE ─────────────────────────────────────────


def test_unpaid_charge_urgency_always_overdue(test_db):
    """Charges only appear after threshold — urgency is always OVERDUE by design."""
    biz = create_business(test_db)
    test_db.add(
        Charge(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=300,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=31),
        )
    )
    test_db.commit()

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    charge_items = [i for i in items if i.source_type == WorkQueueSourceType.CHARGE]

    assert all(i.urgency == WorkQueueUrgency.OVERDUE for i in charge_items)


# ── Linked manual tasks merge ────────────────────────────────────────────────


def _add_task_for_source(
    db,
    *,
    source_domain: str | None,
    source_id: int | None,
    title: str = "Linked task",
    status=TaskStatus.OPEN,
    due_date=None,
) -> Task:
    task = Task(
        title=title,
        status=status,
        priority=TaskPriority.HIGH,
        due_date=due_date,
        source_domain=source_domain,
        source_id=source_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(task)
    db.commit()
    return task


def _add_overdue_charge(db, biz, *, days_ago: int = 31) -> Charge:
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=days_ago),
    )
    db.add(charge)
    db.commit()
    return charge


def test_scope_manual_filters_before_pagination(test_db):
    biz = create_business(test_db)
    _add_overdue_charge(test_db, biz, days_ago=40)
    task = _add_task_for_source(
        test_db,
        source_domain=None,
        source_id=None,
        title="Manual outside first page",
        due_date=utcnow() + timedelta(days=30),
    )

    unfiltered = WorkQueueService(test_db).list_items(limit=1)
    manual_page = WorkQueueService(test_db).list_items(scope="manual", limit=1)

    assert not any(
        item.source_type == WorkQueueSourceType.TASK and item.source_id == task.id
        for item in unfiltered
    )
    assert len(manual_page) == 1
    assert manual_page[0].source_type == WorkQueueSourceType.TASK
    assert manual_page[0].source_id == task.id


def test_search_filters_before_pagination(test_db):
    biz = create_business(test_db)
    _add_overdue_charge(test_db, biz, days_ago=40)
    task = _add_task_for_source(
        test_db,
        source_domain=None,
        source_id=None,
        title="Needle Hebrew משימה",
        due_date=utcnow() + timedelta(days=30),
    )

    items = WorkQueueService(test_db).list_items(search="needle", limit=1)

    assert len(items) == 1
    assert items[0].source_type == WorkQueueSourceType.TASK
    assert items[0].source_id == task.id


def test_source_type_task_returns_task_rows_only(test_db):
    biz = create_business(test_db)
    _add_overdue_charge(test_db, biz)
    _add_task_for_source(test_db, source_domain=None, source_id=None)

    items = WorkQueueService(test_db).list_items(source_type=WorkQueueSourceType.TASK)

    assert items
    assert all(item.source_type == WorkQueueSourceType.TASK for item in items)


def test_scope_system_excludes_task_rows(test_db):
    biz = create_business(test_db)
    _add_overdue_charge(test_db, biz)
    _add_task_for_source(test_db, source_domain=None, source_id=None)

    items = WorkQueueService(test_db).list_items(scope="system")

    assert items
    assert all(item.source_type != WorkQueueSourceType.TASK for item in items)


def test_linked_filters_return_expected_rows(test_db):
    biz = create_business(test_db)
    linked_charge = _add_overdue_charge(test_db, biz, days_ago=31)
    unlinked_charge = _add_overdue_charge(test_db, biz, days_ago=32)
    _add_task_for_source(test_db, source_domain="charge", source_id=linked_charge.id)

    linked = WorkQueueService(test_db).list_items(client_record_id=biz.client_id, linked="linked")
    unlinked = WorkQueueService(test_db).list_items(
        client_record_id=biz.client_id, linked="unlinked"
    )

    assert {item.source_id for item in linked} == {linked_charge.id}
    assert all(item.linked_tasks_count > 0 for item in linked)
    assert unlinked_charge.id in {item.source_id for item in unlinked}
    assert all(item.linked_tasks_count == 0 for item in unlinked)


def test_task_status_open_finds_standalone_task_rows(test_db):
    task = _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.OPEN)

    items = WorkQueueService(test_db).list_items(task_status=TaskStatus.OPEN)

    assert {item.source_id for item in items} == {task.id}


def test_task_status_open_finds_linked_source_rows(test_db):
    biz = create_business(test_db)
    charge = _add_overdue_charge(test_db, biz)
    _add_task_for_source(
        test_db,
        source_domain="charge",
        source_id=charge.id,
        status=TaskStatus.OPEN,
    )

    items = WorkQueueService(test_db).list_items(
        client_record_id=biz.client_id, task_status=TaskStatus.OPEN
    )

    assert len(items) == 1
    assert items[0].source_type == WorkQueueSourceType.CHARGE
    assert items[0].linked_tasks[0].status == TaskStatus.OPEN.value


def test_history_task_status_done_finds_completed_task_rows(test_db):
    task = _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.DONE)

    items = WorkQueueService(test_db).list_items(
        include_task_history=True, task_status=TaskStatus.DONE
    )

    assert {item.source_id for item in items} == {task.id}


def test_active_mode_hides_done_and_canceled_task_rows(test_db):
    _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.DONE)
    _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.CANCELED)

    items = WorkQueueService(test_db).list_items()

    assert not any(item.source_type == WorkQueueSourceType.TASK for item in items)


def test_summary_is_computed_before_pagination_and_respects_filters(test_db):
    biz = create_business(test_db)
    linked_charge = _add_overdue_charge(test_db, biz, days_ago=31)
    _add_overdue_charge(test_db, biz, days_ago=32)
    _add_task_for_source(test_db, source_domain="charge", source_id=linked_charge.id)
    manual = _add_task_for_source(
        test_db,
        source_domain=None,
        source_id=None,
        title="Summary needle",
        due_date=utcnow() + timedelta(days=30),
    )

    service = WorkQueueService(test_db)
    page_response = service.list_items_with_total(limit=1)
    summary = page_response.summary
    searched = service.list_items_with_total(search="summary").summary

    assert len(page_response.items) == 1
    assert summary.total == 3
    assert summary.manual_tasks == 1
    assert summary.linked == 1
    assert summary.overdue == 2
    assert summary.upcoming == 1
    assert summary.by_source_type[WorkQueueSourceType.CHARGE] == 2
    assert summary.by_source_type[WorkQueueSourceType.TASK] == 1
    assert summary.by_task_status[TaskStatus.OPEN.value] == 2
    assert searched.total == 1
    assert searched.by_source_type[WorkQueueSourceType.TASK] == 1
    assert manual.id is not None


def test_summary_respects_history_mode(test_db):
    _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.OPEN)
    _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.DONE)
    _add_task_for_source(test_db, source_domain=None, source_id=None, status=TaskStatus.CANCELED)

    active = WorkQueueService(test_db).list_items_with_total().summary
    history = WorkQueueService(test_db).list_items_with_total(include_task_history=True).summary

    assert active.total == 1
    assert active.by_task_status[TaskStatus.OPEN.value] == 1
    assert history.total == 2
    assert history.by_task_status[TaskStatus.DONE.value] == 1
    assert history.by_task_status[TaskStatus.CANCELED.value] == 1


def test_linked_task_merges_into_source_row(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.flush()
    task = _add_task_for_source(
        test_db, source_domain="charge", source_id=charge.id, title="Call client"
    )

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    charge_rows = [i for i in items if i.source_type == WorkQueueSourceType.CHARGE]
    task_rows = [i for i in items if i.source_type == WorkQueueSourceType.TASK]

    assert len(charge_rows) == 1
    assert charge_rows[0].linked_tasks_count == 1
    assert charge_rows[0].linked_tasks[0].id == task.id
    action_keys = [action.key for action in charge_rows[0].available_actions]
    assert any(key.startswith("continue_task") for key in action_keys)
    assert any(key.startswith("edit_task") for key in action_keys)
    assert not any(i.source_id == task.id for i in task_rows)


def test_search_matches_linked_task_title(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.flush()
    _add_task_for_source(
        test_db,
        source_domain="charge",
        source_id=charge.id,
        title="בדיקת מסמכים",
    )

    items = WorkQueueService(test_db).list_items(search="בדיקת")

    assert any(item.source_type == WorkQueueSourceType.CHARGE for item in items)


def test_multiple_linked_tasks_merge_into_single_source_row(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.flush()
    _add_task_for_source(
        test_db,
        source_domain="charge",
        source_id=charge.id,
        title="בדיקת מסמכים",
    )
    _add_task_for_source(
        test_db,
        source_domain="charge",
        source_id=charge.id,
        title="שיחה עם הלקוח",
    )

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    charge_row = next(i for i in items if i.source_type == WorkQueueSourceType.CHARGE)

    assert charge_row.linked_tasks_count == 2
    assert len(charge_row.linked_tasks) == 2
    action_labels = [action.label for action in charge_row.available_actions]
    assert "פתח משימה: בדיקת מסמכים" in action_labels
    assert "פתח משימה: שיחה עם הלקוח" in action_labels
    assert "ערוך משימה: בדיקת מסמכים" in action_labels
    assert "ערוך משימה: שיחה עם הלקוח" in action_labels


def test_task_linked_to_source_not_in_queue_appears_as_task(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=5),
    )
    test_db.add(charge)
    test_db.flush()
    task = _add_task_for_source(test_db, source_domain="charge", source_id=charge.id)

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    task_row = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )

    assert task_row.source_summary is not None
    assert task_row.source_summary.source_type == "charge"
    assert task_row.warnings == []


def test_final_source_with_open_task_returns_task_warning(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.PAID,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.flush()
    task = _add_task_for_source(test_db, source_domain="charge", source_id=charge.id)

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    task_row = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )

    assert [w.key for w in task_row.warnings] == ["source_final"]


def test_deleted_source_with_open_task_returns_task_warning(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
        deleted_at=utcnow(),
    )
    test_db.add(charge)
    test_db.flush()
    task = _add_task_for_source(test_db, source_domain="charge", source_id=charge.id)

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    task_row = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )

    assert [w.key for w in task_row.warnings] == ["source_missing"]


def test_done_task_does_not_hide_open_source(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.flush()
    _add_task_for_source(
        test_db,
        source_domain="charge",
        source_id=charge.id,
        status=TaskStatus.DONE,
    )

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    charge_row = next(i for i in items if i.source_type == WorkQueueSourceType.CHARGE)

    assert charge_row.linked_tasks_count == 0


def test_done_linked_task_history_does_not_override_source_actions(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.flush()
    task = _add_task_for_source(
        test_db,
        source_domain="charge",
        source_id=charge.id,
        status=TaskStatus.DONE,
    )

    items = WorkQueueService(test_db).list_items(
        client_record_id=biz.client_id,
        include_task_history=True,
    )
    charge_row = next(i for i in items if i.source_type == WorkQueueSourceType.CHARGE)
    task_row = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )

    assert charge_row.linked_tasks_count == 0
    assert [a.key for a in charge_row.available_actions] == [
        "open_charge_context",
        "create_linked_task",
    ]
    assert task_row.source_summary is not None
    assert task_row.source_summary.source_type == "charge"


def test_charge_item_exposes_only_safe_link_actions(test_db):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=500,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today() - timedelta(days=31),
    )
    test_db.add(charge)
    test_db.commit()

    item = next(
        i
        for i in WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
        if i.source_type == WorkQueueSourceType.CHARGE
    )

    assert [a.key for a in item.available_actions] == [
        "open_charge_context",
        "create_linked_task",
    ]


def test_pagination_happens_after_merge(test_db):
    biz = create_business(test_db)
    for idx, days_ago in enumerate([31, 32]):
        charge = Charge(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=500,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=days_ago),
        )
        test_db.add(charge)
        test_db.flush()
        _add_task_for_source(
            test_db,
            source_domain="charge",
            source_id=charge.id,
            title=f"Task {idx}",
        )

    page = WorkQueueService(test_db).list_items(client_record_id=biz.client_id, limit=2, offset=0)

    assert len(page) == 2
    assert all(i.source_type == WorkQueueSourceType.CHARGE for i in page)
    assert all(i.linked_tasks_count == 1 for i in page)
