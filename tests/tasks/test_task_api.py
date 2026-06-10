from datetime import date

import pytest

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.tasks.repositories.task_repository import TaskRepository
from app.utils.time_utils import utcnow
from tests.helpers.task_helpers import create_business, create_charge

# ── Create ────────────────────────────────────────────────────────────────────


def test_create_standalone_task_is_open_active_and_unlinked(client, test_db, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Standalone queue task"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    task = TaskRepository(test_db).get_by_id(task_id)
    assert task is not None
    assert task.deleted_at is None
    assert task.status.value == "open"
    assert task.source_domain is None
    assert task.source_id is None
    data = resp.json()
    assert data["title"] == "Standalone queue task"
    assert data["status"] == "open"
    assert data["priority"] == "normal"


def test_create_standalone_task_appears_in_work_queue_api(client, advisor_headers):
    created = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Find me in queue"},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    resp = client.get("/api/v1/work-queue", headers=advisor_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    match = next(
        (item for item in items if item["source_type"] == "task" and item["source_id"] == task_id),
        None,
    )
    assert match is not None
    assert match["title"] == "Find me in queue"
    assert match["metadata"]["source_domain"] is None
    assert match["metadata"]["source_id"] is None


def test_create_task_persists_due_date(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Due task", "due_date": "2026-06-15"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["due_date"] == "2026-06-15"


def test_update_task_persists_due_date(client, advisor_headers):
    created = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Due update"},
    ).json()

    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"due_date": "2026-07-20"},
    )
    assert resp.status_code == 200
    assert resp.json()["due_date"] == "2026-07-20"


def test_create_task_with_optional_fields(client, test_db, advisor_headers):
    biz = create_business(test_db)
    charge = create_charge(test_db, biz.client_id, biz.id)
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={
            "title": "Rich Task",
            "description": "Some details",
            "priority": "high",
            "source_domain": "charge",
            "source_id": charge.id,
            "action_key": "review_charge",
            "action_payload": {"charge_id": charge.id},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["priority"] == "high"
    assert data["source_domain"] == "charge"
    assert data["action_payload"] == {"charge_id": charge.id}


def test_create_task_requires_title(client, advisor_headers):
    resp = client.post("/api/v1/tasks", headers=advisor_headers, json={})
    assert resp.status_code == 422


# ── List ──────────────────────────────────────────────────────────────────────


def test_list_tasks_empty(client, advisor_headers):
    resp = client.get("/api/v1/tasks", headers=advisor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_get_nonexistent_task(client, advisor_headers):
    resp = client.get("/api/v1/tasks/99999", headers=advisor_headers)
    assert resp.status_code == 404


def test_delete_task_soft_deletes(client, advisor_headers):
    created = client.post(
        "/api/v1/tasks", headers=advisor_headers, json={"title": "Delete Me"}
    ).json()
    resp = client.delete(f"/api/v1/tasks/{created['id']}", headers=advisor_headers)
    assert resp.status_code == 204

    get_resp = client.get(f"/api/v1/tasks/{created['id']}", headers=advisor_headers)
    assert get_resp.status_code == 404


def test_create_task_rejects_unknown_source_domain(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Bad source", "source_domain": "unpaid_charge", "source_id": 1},
    )
    assert resp.status_code == 400


def test_create_task_rejects_partial_source_link_domain_only(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Bad source", "source_domain": "charge"},
    )
    assert resp.status_code == 400


def test_create_task_rejects_partial_source_link_id_only(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Bad source", "source_id": 1},
    )
    assert resp.status_code == 400


def test_create_task_rejects_missing_linked_source(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={
            "title": "Missing source",
            "source_domain": "charge",
            "source_id": 99999,
        },
    )
    assert resp.status_code == 404


def test_create_task_rejects_deleted_linked_source(client, test_db, advisor_headers):
    biz = create_business(test_db)
    charge = Charge(
        client_record_id=biz.client_id,
        business_id=biz.id,
        amount=100,
        charge_type=ChargeType.OTHER,
        status=ChargeStatus.ISSUED,
        issued_at=date.today(),
        deleted_at=utcnow(),
    )
    test_db.add(charge)
    test_db.commit()

    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={
            "title": "Deleted source",
            "source_domain": "charge",
            "source_id": charge.id,
        },
    )
    assert resp.status_code == 404


def test_secretary_can_access_tasks(client, secretary_headers):
    resp = client.get("/api/v1/tasks", headers=secretary_headers)
    assert resp.status_code == 200


def test_secretary_can_manage_tasks(client, secretary_headers):
    created = client.post(
        "/api/v1/tasks", headers=secretary_headers, json={"title": "Secretary task"}
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    assert (
        client.patch(
            f"/api/v1/tasks/{task_id}",
            headers=secretary_headers,
            json={"title": "Updated by secretary"},
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/tasks/{task_id}/complete", headers=secretary_headers).status_code
        == 200
    )

    deletable = client.post(
        "/api/v1/tasks",
        headers=secretary_headers,
        json={"title": "Delete by secretary"},
    ).json()
    assert (
        client.delete(f"/api/v1/tasks/{deletable['id']}", headers=secretary_headers).status_code
        == 204
    )


# ── Pagination total > page_size ──────────────────────────────────────────────


def test_list_pagination_total_reflects_all_items(client, advisor_headers):
    for i in range(5):
        client.post("/api/v1/tasks", headers=advisor_headers, json={"title": f"Task {i}"})

    resp = client.get("/api/v1/tasks?page=1&page_size=3", headers=advisor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 3


# ── assigned_role validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("assigned_role", ["advisor", "secretary"])
def test_create_task_accepts_valid_assigned_role(client, advisor_headers, assigned_role):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Role Task", "assigned_role": assigned_role},
    )
    assert resp.status_code == 201
    assert resp.json()["assigned_role"] == assigned_role


def test_create_task_invalid_assigned_role_rejected(client, advisor_headers):
    resp = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Bad Role", "assigned_role": "superadmin"},
    )
    assert resp.status_code == 422


def test_update_task_invalid_assigned_role_rejected(client, advisor_headers):
    created = client.post("/api/v1/tasks", headers=advisor_headers, json={"title": "Task"}).json()
    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"assigned_role": "manager"},
    )
    assert resp.status_code == 422


# ── Source linking via PATCH ──────────────────────────────────────────────────


def test_patch_task_links_valid_source(client, test_db, advisor_headers):
    biz = create_business(test_db)
    charge = create_charge(test_db, biz.client_id, biz.id)

    created = client.post(
        "/api/v1/tasks", headers=advisor_headers, json={"title": "Linkable"}
    ).json()

    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"source_domain": "charge", "source_id": charge.id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_domain"] == "charge"
    assert data["source_id"] == charge.id


def test_patch_task_relinks_from_one_valid_source_to_another(client, test_db, advisor_headers):
    biz = create_business(test_db)
    first_charge = create_charge(test_db, biz.client_id, biz.id)
    second_charge = create_charge(test_db, biz.client_id, biz.id)

    created = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={
            "title": "Relinkable",
            "source_domain": "charge",
            "source_id": first_charge.id,
        },
    ).json()

    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"source_domain": "charge", "source_id": second_charge.id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_domain"] == "charge"
    assert data["source_id"] == second_charge.id


@pytest.mark.parametrize(
    "payload",
    [
        {"source_domain": "charge"},
        {"source_id": 1},
    ],
)
def test_patch_task_partial_source_link_rejected(client, advisor_headers, payload):
    created = client.post(
        "/api/v1/tasks", headers=advisor_headers, json={"title": "Partial source"}
    ).json()
    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json=payload,
    )
    assert resp.status_code == 400


def test_patch_linked_task_partial_source_update_rejected(client, test_db, advisor_headers):
    biz = create_business(test_db)
    charge = create_charge(test_db, biz.client_id, biz.id)

    created = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={
            "title": "Already linked",
            "source_domain": "charge",
            "source_id": charge.id,
        },
    ).json()

    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"source_domain": "binder"},
    )
    assert resp.status_code == 400


def test_patch_task_unknown_source_domain_rejected(client, advisor_headers):
    created = client.post(
        "/api/v1/tasks", headers=advisor_headers, json={"title": "Bad domain"}
    ).json()
    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"source_domain": "unknown_domain", "source_id": 1},
    )
    assert resp.status_code == 400


def test_patch_task_missing_source_record_rejected(client, advisor_headers):
    created = client.post(
        "/api/v1/tasks", headers=advisor_headers, json={"title": "Missing source"}
    ).json()
    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"source_domain": "charge", "source_id": 99999},
    )
    assert resp.status_code == 404


def test_patch_task_clears_source_with_explicit_null(client, test_db, advisor_headers):
    biz = create_business(test_db)
    charge = create_charge(test_db, biz.client_id, biz.id)

    created = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={"title": "Clearable", "source_domain": "charge", "source_id": charge.id},
    ).json()
    assert created["source_domain"] == "charge"

    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"source_domain": None, "source_id": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_domain"] is None
    assert data["source_id"] is None


def test_patch_task_without_source_fields_does_not_clear_existing_source(
    client, test_db, advisor_headers
):
    biz = create_business(test_db)
    charge = create_charge(test_db, biz.client_id, biz.id)

    created = client.post(
        "/api/v1/tasks",
        headers=advisor_headers,
        json={
            "title": "Keep source",
            "source_domain": "charge",
            "source_id": charge.id,
        },
    ).json()

    resp = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=advisor_headers,
        json={"title": "Updated title only"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_domain"] == "charge"
    assert data["source_id"] == charge.id
