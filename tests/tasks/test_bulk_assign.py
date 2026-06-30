"""Tests for POST /api/v1/tasks/bulk-assign."""

import uuid

from app.tasks.schemas.task import TaskCreateRequest
from app.tasks.services.task_service import TaskService
from app.users.models.user import UserRole
from tests.factories import create_user


def _task(db, **kwargs):
    req = TaskCreateRequest(title="Bulk assign task", **kwargs)
    return TaskService(db).create(req, created_by_user_id=None)


def _idem():
    return str(uuid.uuid4())


def _post(client, headers, task_ids, assignee_user_id, idem_key=None):
    return client.post(
        "/api/v1/tasks/bulk-assign",
        headers={**headers, "X-Idempotency-Key": idem_key or _idem()},
        json={"task_ids": task_ids, "assignee_user_id": assignee_user_id},
    )


def _create_user(db, email="assignee@example.com", active=True):
    user = create_user(
        db,
        full_name="Assignee User",
        email=email,
        password="password123",
        role=UserRole.ADVISOR,
        is_active=active,
    )
    return user


# ── Success ───────────────────────────────────────────────────────────────────


def test_bulk_assign_sets_assignee(client, test_db, advisor_headers):
    t1 = _task(test_db)
    t2 = _task(test_db)
    assignee = _create_user(test_db)

    resp = _post(client, advisor_headers, [t1.id, t2.id], assignee.id)
    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["succeeded"]) == sorted([t1.id, t2.id])
    assert data["failed"] == []

    updated = TaskService(test_db).get(t1.id)
    assert updated.assigned_to_user_id == assignee.id


def test_bulk_assign_null_unassigns(client, test_db, advisor_headers):
    assignee = _create_user(test_db)
    t = _task(test_db, assigned_to_user_id=assignee.id)

    resp = _post(client, advisor_headers, [t.id], None)
    assert resp.status_code == 200
    assert t.id in resp.json()["succeeded"]
    assert TaskService(test_db).get(t.id).assigned_to_user_id is None


def test_same_assignee_already_is_idempotent_success(client, test_db, advisor_headers):
    assignee = _create_user(test_db)
    t = _task(test_db, assigned_to_user_id=assignee.id)

    resp = _post(client, advisor_headers, [t.id], assignee.id)
    assert resp.status_code == 200
    assert t.id in resp.json()["succeeded"]
    assert resp.json()["failed"] == []


def test_already_null_assign_null_is_success(client, test_db, advisor_headers):
    t = _task(test_db)  # assigned_to_user_id = None by default
    resp = _post(client, advisor_headers, [t.id], None)
    assert resp.status_code == 200
    assert t.id in resp.json()["succeeded"]


# ── Terminal state ────────────────────────────────────────────────────────────


def test_done_task_fails_with_conflict(client, test_db, advisor_headers):
    t = _task(test_db)
    TaskService(test_db).complete(t.id, completed_by_user_id=None)
    assignee = _create_user(test_db, email="a2@example.com")

    resp = _post(client, advisor_headers, [t.id], assignee.id)
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] == []
    assert data["failed"][0]["task_id"] == t.id
    assert data["failed"][0]["code"] == "TASK.CONFLICT"


def test_canceled_task_fails_with_conflict(client, test_db, advisor_headers):
    t = _task(test_db)
    TaskService(test_db).cancel(t.id)
    assignee = _create_user(test_db, email="a3@example.com")

    resp = _post(client, advisor_headers, [t.id], assignee.id)
    assert resp.status_code == 200
    assert resp.json()["failed"][0]["code"] == "TASK.CONFLICT"


# ── Invalid assignee (whole-request fail) ─────────────────────────────────────


def test_nonexistent_assignee_fails_whole_request(client, test_db, advisor_headers):
    t = _task(test_db)
    resp = _post(client, advisor_headers, [t.id], 999999)
    assert resp.status_code == 404
    assert TaskService(test_db).get(t.id).assigned_to_user_id is None


def test_inactive_assignee_fails_whole_request(client, test_db, advisor_headers):
    inactive = _create_user(test_db, email="inactive@example.com", active=False)
    t = _task(test_db)

    resp = _post(client, advisor_headers, [t.id], inactive.id)
    assert resp.status_code == 404


# ── Missing task ──────────────────────────────────────────────────────────────


def test_missing_task_id_returns_not_found_in_result(client, advisor_headers):
    resp = _post(client, advisor_headers, [999999], None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"][0]["code"] == "TASK.NOT_FOUND"


# ── Partial success ───────────────────────────────────────────────────────────


def test_partial_success(client, test_db, advisor_headers):
    ok_task = _task(test_db)
    done_task = _task(test_db)
    TaskService(test_db).complete(done_task.id, completed_by_user_id=None)
    assignee = _create_user(test_db, email="partial@example.com")

    resp = _post(client, advisor_headers, [ok_task.id, done_task.id], assignee.id)
    assert resp.status_code == 200
    data = resp.json()
    assert ok_task.id in data["succeeded"]
    assert any(f["task_id"] == done_task.id for f in data["failed"])


def test_duplicate_ids_deduplicated(client, test_db, advisor_headers):
    t = _task(test_db)
    resp = _post(client, advisor_headers, [t.id, t.id], None)
    assert resp.status_code == 200
    assert resp.json()["succeeded"].count(t.id) == 1


# ── Idempotency ───────────────────────────────────────────────────────────────


def test_missing_idempotency_key_returns_422(client, test_db, advisor_headers):
    t = _task(test_db)
    resp = client.post(
        "/api/v1/tasks/bulk-assign",
        headers=advisor_headers,
        json={"task_ids": [t.id], "assignee_user_id": None},
    )
    assert resp.status_code == 422


def test_same_key_different_payload_returns_409(client, test_db, advisor_headers):
    t1 = _task(test_db)
    t2 = _task(test_db)
    key = _idem()
    r1 = _post(client, advisor_headers, [t1.id], None, idem_key=key)
    assert r1.status_code == 200
    r2 = _post(client, advisor_headers, [t2.id], None, idem_key=key)
    assert r2.status_code == 409


def test_replay_same_key_returns_same_response(client, test_db, advisor_headers):
    t = _task(test_db)
    key = _idem()
    r1 = _post(client, advisor_headers, [t.id], None, idem_key=key)
    r2 = _post(client, advisor_headers, [t.id], None, idem_key=key)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


# ── Validation ────────────────────────────────────────────────────────────────


def test_empty_task_ids_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-assign",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": [], "assignee_user_id": None},
    )
    assert resp.status_code == 422


def test_over_100_ids_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-assign",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": list(range(1, 102)), "assignee_user_id": None},
    )
    assert resp.status_code == 422


def test_negative_id_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-assign",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": [-1], "assignee_user_id": None},
    )
    assert resp.status_code == 422


def test_negative_assignee_user_id_returns_422(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks/bulk-assign",
        headers={**advisor_headers, "X-Idempotency-Key": _idem()},
        json={"task_ids": [1], "assignee_user_id": -5},
    )
    assert resp.status_code == 422


# ── Auth ─────────────────────────────────────────────────────────────────────


def test_unauthenticated_returns_401(client, test_db):
    t = _task(test_db)
    resp = client.post(
        "/api/v1/tasks/bulk-assign",
        headers={"X-Idempotency-Key": _idem()},
        json={"task_ids": [t.id], "assignee_user_id": None},
    )
    assert resp.status_code == 401


def test_secretary_allowed(client, test_db, secretary_headers):
    t = _task(test_db)
    resp = _post(client, secretary_headers, [t.id], None)
    assert resp.status_code == 200
