"""Tests for POST /api/v1/tasks/bulk-complete."""

import uuid

from app.tasks.models.task import TaskStatus
from app.tasks.schemas.task import TaskCreateRequest
from app.tasks.services.task_service import TaskService


def _task(db, **kwargs):
    req = TaskCreateRequest(title="Bulk complete task", **kwargs)
    return TaskService(db).create(req, created_by_user_id=None)


def _idem():
    return str(uuid.uuid4())


def _post(client, headers, task_ids, idem_key=None):
    return client.post(
        "/api/v1/tasks/bulk-complete",
        headers={**headers, "X-Idempotency-Key": idem_key or _idem()},
        json={"task_ids": task_ids},
    )


# ── Success ───────────────────────────────────────────────────────────────────


def test_bulk_complete_marks_tasks_done(client, test_db, advisor_headers):
    t1 = _task(test_db)
    t2 = _task(test_db)

    resp = _post(client, advisor_headers, [t1.id, t2.id])
    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["succeeded"]) == sorted([t1.id, t2.id])
    assert data["failed"] == []

    task1 = TaskService(test_db).get(t1.id)
    assert task1.status == TaskStatus.DONE
    assert task1.completed_at is not None


def test_already_done_is_idempotent_success(client, test_db, advisor_headers):
    t = _task(test_db)
    TaskService(test_db).complete(t.id, completed_by_user_id=None)
    original_completed_at = TaskService(test_db).get(t.id).completed_at

    resp = _post(client, advisor_headers, [t.id])
    assert resp.status_code == 200
    data = resp.json()
    assert t.id in data["succeeded"]
    assert data["failed"] == []
    assert TaskService(test_db).get(t.id).completed_at == original_completed_at


def test_canceled_task_fails_with_conflict(client, test_db, advisor_headers):
    t = _task(test_db)
    TaskService(test_db).cancel(t.id)

    resp = _post(client, advisor_headers, [t.id])
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == []
    assert len(data["failed"]) == 1
    assert data["failed"][0]["task_id"] == t.id
    assert data["failed"][0]["code"] == "TASK.CONFLICT"


def test_missing_task_fails_with_not_found(client, advisor_headers):
    resp = _post(client, advisor_headers, [999999])
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == []
    assert data["failed"][0]["code"] == "TASK.NOT_FOUND"


def test_partial_success(client, test_db, advisor_headers):
    ok_task = _task(test_db)
    canceled_task = _task(test_db)
    TaskService(test_db).cancel(canceled_task.id)

    resp = _post(client, advisor_headers, [ok_task.id, canceled_task.id])
    assert resp.status_code == 200
    data = resp.json()
    assert ok_task.id in data["succeeded"]
    assert any(f["task_id"] == canceled_task.id for f in data["failed"])


def test_duplicate_ids_deduplicated(client, test_db, advisor_headers):
    t = _task(test_db)
    resp = _post(client, advisor_headers, [t.id, t.id, t.id])
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"].count(t.id) == 1


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_missing_idempotency_key_returns_422(client, test_db, advisor_headers):
    t = _task(test_db)
    resp = client.post(
        "/api/v1/tasks/bulk-complete",
        headers=advisor_headers,
        json={"task_ids": [t.id]},
    )
    assert resp.status_code == 422


def test_replay_same_key_returns_same_response(client, test_db, advisor_headers):
    t = _task(test_db)
    key = _idem()
    r1 = _post(client, advisor_headers, [t.id], idem_key=key)
    r2 = _post(client, advisor_headers, [t.id], idem_key=key)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


# ── Validation ────────────────────────────────────────────────────────────────


def test_empty_task_ids_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-complete",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": []},
    )
    assert resp.status_code == 422


def test_over_100_ids_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-complete",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": list(range(1, 102))},
    )
    assert resp.status_code == 422


def test_negative_id_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-complete",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": [-1]},
    )
    assert resp.status_code == 422


def test_same_key_different_payload_returns_409(client, test_db, advisor_headers):
    t1 = _task(test_db)
    t2 = _task(test_db)
    key = _idem()
    r1 = _post(client, advisor_headers, [t1.id], idem_key=key)
    assert r1.status_code == 200
    r2 = _post(client, advisor_headers, [t2.id], idem_key=key)
    assert r2.status_code == 409


def test_secretary_allowed(client, test_db, secretary_headers):
    t = _task(test_db)
    resp = _post(client, secretary_headers, [t.id])
    assert resp.status_code == 200
