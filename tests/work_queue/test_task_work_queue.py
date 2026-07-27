"""Work queue integration tests for persisted Task items."""

from datetime import date, timedelta

from app.charges.models.charge import ChargeStatus, ChargeType
from app.tasks.models.task import TaskPriority, TaskStatus
from app.utils.time_utils import utcnow
from app.work_queue.schemas.work_queue import WorkQueueSourceType, WorkQueueUrgency
from app.work_queue.services.work_queue_service import WorkQueueService

# ── Inclusion ─────────────────────────────────────────────────────────────────


def test_open_task_appears_in_work_queue(test_db, task_factory):
    task = task_factory(title="Open Task", status=TaskStatus.OPEN, commit=True)
    items = WorkQueueService(test_db).list_items()
    task_items = [i for i in items if i.source_type == WorkQueueSourceType.TASK]
    assert any(i.source_id == task.id for i in task_items)


def test_open_standalone_task_can_be_filtered_with_many_system_rows(
    test_db, create_client_with_business, charge_factory, task_factory
):
    _, biz = create_client_with_business(full_name="Task Test Client")
    for _ in range(55):
        charge_factory(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=100,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=utcnow().date() - timedelta(days=31),
        )
    task = task_factory(title="Manual task in first page", status=TaskStatus.OPEN, commit=True)

    items = WorkQueueService(test_db).list_items(scope="manual")
    task_items = [i for i in items if i.source_type == WorkQueueSourceType.TASK]

    assert any(i.source_id == task.id for i in task_items)
    match = next(i for i in task_items if i.source_id == task.id)
    assert match.source_type == WorkQueueSourceType.TASK
    assert match.metadata["source_domain"] is None
    assert match.metadata["source_id"] is None


# ── Null due_date ─────────────────────────────────────────────────────────────


def test_null_due_date_task_appears(test_db, task_factory):
    task = task_factory(title="No Due Date", status=TaskStatus.OPEN, commit=True)
    items = WorkQueueService(test_db).list_items()
    match = next(
        (i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id),
        None,
    )
    assert match is not None
    assert match.due_date is None
    assert match.urgency == WorkQueueUrgency.UPCOMING


def test_null_due_date_task_sorts_after_dated_task(test_db, task_factory):
    task_factory(title="Dated", status=TaskStatus.OPEN, due_date=utcnow(), commit=True)
    task_factory(title="Undated", status=TaskStatus.OPEN, due_date=None, commit=True)

    items = WorkQueueService(test_db).list_items()
    task_items = [i for i in items if i.source_type == WorkQueueSourceType.TASK]

    dated = next(i for i in task_items if i.due_date is not None)
    undated = next(i for i in task_items if i.due_date is None)
    assert task_items.index(dated) < task_items.index(undated)


# ── Urgency from due_date ─────────────────────────────────────────────────────


def test_overdue_task_urgency(test_db, task_factory):
    past = utcnow() - timedelta(days=2)
    task = task_factory(status=TaskStatus.OPEN, due_date=past, commit=True)
    items = WorkQueueService(test_db).list_items()
    match = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )
    assert match.urgency == WorkQueueUrgency.OVERDUE


def test_approaching_task_urgency(test_db, task_factory):
    soon = utcnow() + timedelta(days=3)
    task = task_factory(status=TaskStatus.OPEN, due_date=soon, commit=True)
    items = WorkQueueService(test_db).list_items()
    match = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )
    assert match.urgency == WorkQueueUrgency.APPROACHING


# ── Metadata ──────────────────────────────────────────────────────────────────


def test_task_work_queue_item_metadata(test_db, task_factory, actor_user):
    task = task_factory(
        title="Payload Task",
        status=TaskStatus.OPEN,
        priority=TaskPriority.HIGH,
        description="Some details",
        assigned_to_user_id=actor_user.id,
        assigned_role="advisor",
        action_key="review",
        action_payload={"key": "val"},
        source_domain="charge",
        source_id=42,
        commit=True,
    )

    items = WorkQueueService(test_db).list_items()
    match = next(
        i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id
    )

    assert match.title == "Payload Task"
    assert match.metadata["status"] == "open"
    assert match.metadata["priority"] == "high"
    assert match.metadata["description"] == "Some details"
    assert match.metadata["assigned_to_user_id"] == actor_user.id
    assert match.metadata["assigned_role"] == "advisor"
    assert match.metadata["action_key"] == "review"
    assert match.metadata["action_payload"] == {"key": "val"}
    assert match.metadata["source_domain"] == "charge"
    assert match.metadata["source_id"] == 42


# ── Exclusion filter ──────────────────────────────────────────────────────────


def test_exclude_task_source_type(test_db, task_factory):
    task_factory(status=TaskStatus.OPEN, commit=True)
    items = WorkQueueService(test_db).list_items(exclude_source_types=[WorkQueueSourceType.TASK])
    assert not any(i.source_type == WorkQueueSourceType.TASK for i in items)


# ── Tasks hidden when client_record_id filter is active ──────────────────────


def test_tasks_hidden_when_client_scoped(test_db, task_factory):
    task_factory(title="Global Task", status=TaskStatus.OPEN, commit=True)
    items = WorkQueueService(test_db).list_items(client_record_id=1)
    assert not any(i.source_type == WorkQueueSourceType.TASK for i in items)


# ── Source-linked task enrichment ─────────────────────────────────────────────


def test_task_linked_to_charge_exposes_client_info(
    test_db, create_client_with_business, charge_factory, task_factory
):
    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = charge_factory(
        client_record_id=biz.client_id,
        business_id=biz.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today(),
        commit=True,
    )

    # Task linked to the charge but charge is not in active work-queue window —
    # task becomes standalone with source enrichment.
    task = task_factory(
        title="Charge Task",
        status=TaskStatus.OPEN,
        priority=TaskPriority.NORMAL,
        source_domain="charge",
        source_id=charge.id,
        commit=True,
    )

    items = WorkQueueService(test_db).list_items()
    match = next(
        (i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id),
        None,
    )
    assert match is not None
    assert match.client_record_id == biz.client_id
    assert match.client_name is not None
    assert match.office_client_number == 100001


def test_task_linked_to_charge_appears_in_client_filtered_work_queue(
    test_db, create_client_with_business, charge_factory, task_factory
):
    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = charge_factory(
        client_record_id=biz.client_id,
        business_id=biz.id,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today(),
        commit=True,
    )

    task = task_factory(
        title="Client Filtered Task",
        status=TaskStatus.OPEN,
        priority=TaskPriority.NORMAL,
        source_domain="charge",
        source_id=charge.id,
        commit=True,
    )

    items = WorkQueueService(test_db).list_items(client_record_id=biz.client_id)
    match = next(
        (i for i in items if i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id),
        None,
    )
    assert match is not None
    assert match.client_record_id == biz.client_id


def test_task_linked_to_other_client_charge_excluded_from_client_filter(
    test_db, create_client_with_business, charge_factory, task_factory
):
    _, biz1 = create_client_with_business(full_name="Task Test Client")
    _, biz2 = create_client_with_business(full_name="Task Test Client")
    charge = charge_factory(
        client_record_id=biz1.client_id,
        business_id=biz1.id,
        amount=100,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=utcnow().date(),
    )

    task = task_factory(
        title="Wrong Client Task",
        status=TaskStatus.OPEN,
        priority=TaskPriority.NORMAL,
        source_domain="charge",
        source_id=charge.id,
        commit=True,
    )

    items = WorkQueueService(test_db).list_items(client_record_id=biz2.client_id)
    assert not any(
        i.source_type == WorkQueueSourceType.TASK and i.source_id == task.id for i in items
    )
