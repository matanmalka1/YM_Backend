"""Tests for GET /api/v1/clients/{client_record_id}/tasks endpoint."""

from app.tasks.schemas.task import TaskCreateRequest
from app.tasks.services.task_service import TaskService
from tests.helpers.task_helpers import create_business, create_charge


def _task(db, **kwargs):
    req = TaskCreateRequest(title="Client task", **kwargs)
    return TaskService(db).create(req, created_by_user_id=None)


def test_returns_tasks_for_client(client, test_db, advisor_headers):
    biz = create_business(test_db)
    _task(test_db, client_record_id=biz.client_id)
    _task(test_db, client_record_id=biz.client_id)

    resp = client.get(f"/api/v1/clients/{biz.client_id}/tasks", headers=advisor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(t["client_record_id"] == biz.client_id for t in data["items"])


def test_excludes_global_tasks(client, test_db, advisor_headers):
    biz = create_business(test_db)
    _task(test_db, client_record_id=biz.client_id)
    _task(test_db)  # global task — no client

    resp = client.get(f"/api/v1/clients/{biz.client_id}/tasks", headers=advisor_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_cross_client_isolation(client, test_db, advisor_headers):
    biz1 = create_business(test_db)
    biz2 = create_business(test_db)
    _task(test_db, client_record_id=biz1.client_id)
    _task(test_db, client_record_id=biz2.client_id)

    resp = client.get(f"/api/v1/clients/{biz1.client_id}/tasks", headers=advisor_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["client_record_id"] == biz1.client_id


def test_nonexistent_client_returns_404(client, advisor_headers):
    resp = client.get("/api/v1/clients/999999/tasks", headers=advisor_headers)
    assert resp.status_code == 404


def test_status_filter(client, test_db, advisor_headers):
    biz = create_business(test_db)
    t1 = _task(test_db, client_record_id=biz.client_id)
    _task(test_db, client_record_id=biz.client_id)
    TaskService(test_db).complete(t1.id, completed_by_user_id=None)

    resp = client.get(f"/api/v1/clients/{biz.client_id}/tasks?status=done", headers=advisor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "done"


def test_pagination(client, test_db, advisor_headers):
    biz = create_business(test_db)
    for _ in range(5):
        _task(test_db, client_record_id=biz.client_id)

    resp = client.get(
        f"/api/v1/clients/{biz.client_id}/tasks?page=1&page_size=2", headers=advisor_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


def test_source_linked_task_appears_for_client(client, test_db, advisor_headers):
    biz = create_business(test_db)
    charge = create_charge(test_db, biz.client_id, biz.id)
    _task(test_db, source_domain="charge", source_id=charge.id)

    resp = client.get(f"/api/v1/clients/{biz.client_id}/tasks", headers=advisor_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_unauthenticated_returns_401(client, test_db):
    biz = create_business(test_db)
    resp = client.get(f"/api/v1/clients/{biz.client_id}/tasks")
    assert resp.status_code == 401


def test_secretary_allowed(client, test_db, secretary_headers):
    biz = create_business(test_db)
    resp = client.get(f"/api/v1/clients/{biz.client_id}/tasks", headers=secretary_headers)
    assert resp.status_code == 200
