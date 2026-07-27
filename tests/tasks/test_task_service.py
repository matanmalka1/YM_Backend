import pytest

from app.charges.models.charge import ChargeStatus, ChargeType
from app.core.exceptions import ConflictError, NotFoundError
from app.tasks.models.task import TaskPriority, TaskStatus
from app.tasks.repositories.task_repository import TaskRepository
from app.tasks.schemas.task import TaskCreateRequest, TaskUpdateRequest
from app.tasks.services.task_service import TaskService


def _create(db, title="Test Task", **kwargs) -> int:
    req = TaskCreateRequest(title=title, **kwargs)
    task = TaskService(db).create(req, created_by_user_id=None)
    return task.id


# ── Lifecycle transitions ─────────────────────────────────────────────────────


def test_create_task_defaults(test_db):
    task_id = _create(test_db)
    task = TaskRepository(test_db).get_by_id(task_id)
    assert task.status == TaskStatus.OPEN
    assert task.priority == TaskPriority.NORMAL
    assert task.deleted_at is None


def test_open_to_done(test_db):
    task_id = _create(test_db)
    result = TaskService(test_db).complete(task_id, completed_by_user_id=None)
    assert result.status == TaskStatus.DONE
    assert result.completed_at is not None


def test_open_to_canceled(test_db):
    task_id = _create(test_db)
    result = TaskService(test_db).cancel(task_id)
    assert result.status == TaskStatus.CANCELED
    assert result.canceled_at is not None


def test_completed_by_user_id_set(test_db):
    task_id = _create(test_db)
    result = TaskService(test_db).complete(task_id, completed_by_user_id=99)
    assert result.completed_by_user_id == 99


# ── Terminal state rejections ─────────────────────────────────────────────────


def test_cannot_complete_canceled_task(test_db):
    task_id = _create(test_db)
    TaskService(test_db).cancel(task_id)
    with pytest.raises(ConflictError):
        TaskService(test_db).complete(task_id, completed_by_user_id=None)


def test_cannot_cancel_done_task(test_db):
    task_id = _create(test_db)
    TaskService(test_db).complete(task_id, completed_by_user_id=None)
    with pytest.raises(ConflictError):
        TaskService(test_db).cancel(task_id)


def test_cannot_update_done_task(test_db):
    task_id = _create(test_db)
    TaskService(test_db).complete(task_id, completed_by_user_id=None)
    with pytest.raises(ConflictError):
        TaskService(test_db).update(task_id, TaskUpdateRequest(title="new"))


def test_cannot_update_canceled_task(test_db):
    task_id = _create(test_db)
    TaskService(test_db).cancel(task_id)
    with pytest.raises(ConflictError):
        TaskService(test_db).update(task_id, TaskUpdateRequest(title="new"))


# ── Not found ─────────────────────────────────────────────────────────────────


def test_get_nonexistent_task_raises(test_db):
    with pytest.raises(NotFoundError):
        TaskService(test_db).get(99999)


# ── Filters ───────────────────────────────────────────────────────────────────


def test_list_filter_by_status(test_db):
    _create(test_db, title="Open task")
    t2 = _create(test_db, title="Done task")
    TaskService(test_db).complete(t2, completed_by_user_id=None)

    items, total = TaskService(test_db).list(status=TaskStatus.OPEN)
    assert total == 1
    assert items[0].title == "Open task"


def test_list_filter_by_priority(test_db):
    _create(test_db, title="Normal", priority=TaskPriority.NORMAL)
    _create(test_db, title="Urgent", priority=TaskPriority.URGENT)

    items, total = TaskService(test_db).list(priority=TaskPriority.URGENT)
    assert total == 1
    assert items[0].title == "Urgent"


def test_list_filter_by_source_domain(test_db, create_client_with_business, charge_factory):
    _, biz = create_client_with_business(full_name="Task Test Client")
    charge = charge_factory(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=100,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        commit=True,
    )
    _create(test_db, title="From charges", source_domain="charge", source_id=charge.id)
    _create(test_db, title="Other")

    items, total = TaskService(test_db).list(source_domain="charge")
    assert total == 1
    assert items[0].source_domain == "charge"


def test_list_pagination(test_db):
    for i in range(5):
        _create(test_db, title=f"Task {i}")

    page1, total = TaskService(test_db).list(page=1, page_size=3)
    page2, _ = TaskService(test_db).list(page=2, page_size=3)
    assert total == 5
    assert len(page1) == 3
    assert len(page2) == 2


def test_list_searches_title_and_description_and_sorts_by_title(test_db):
    _create(test_db, title="Zulu", description="מסמכים מיוחדים")
    _create(test_db, title="Alpha", description="אחר")
    _create(test_db, title="Beta", description="מסמכים נוספים")

    items, total = TaskService(test_db).list(search="מסמכים", sort_by="title", order="asc")

    assert total == 2
    assert [item.title for item in items] == ["Beta", "Zulu"]


def test_enriched_list_summary_ignores_only_status_filter(test_db):
    open_id = _create(test_db, title="Open")
    done_id = _create(test_db, title="Done")
    TaskService(test_db).complete(done_id, completed_by_user_id=None)

    items, total, summary = TaskService(test_db).list_enriched(status=TaskStatus.OPEN)

    assert [item.id for item in items] == [open_id]
    assert total == 1
    assert summary.total == 2
    assert summary.open == 1
    assert summary.done == 1
