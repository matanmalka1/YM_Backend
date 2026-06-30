from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_VAT_WORK_ITEM_DELETED,
    ACTION_VAT_WORK_ITEM_UPDATED,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.vat.models.vat_work_item import VatWorkItem
from tests.vat.api.test_vat_reports_utils import create_work_item, setup_ready_item


def _audit_actions(test_db, item_id: int) -> list[str]:
    return list(
        test_db.scalars(
            select(EntityAuditLog.action).where(
                EntityAuditLog.entity_type == ENTITY_VAT_WORK_ITEM,
                EntityAuditLog.entity_id == item_id,
            )
        )
    )


def _file_item(client, headers, item_id: int):
    response = client.post(
        f"/api/v1/vat/work-items/{item_id}/file",
        headers=headers,
        json={"submission_method": "online"},
    )
    assert response.status_code == 200


def test_patch_one_field_does_not_reset_another(client, advisor_headers, vat_client, test_user):
    response = client.post(
        "/api/v1/vat/work-items",
        headers=advisor_headers,
        json={
            "client_record_id": vat_client.id,
            "period": "2026-01",
            "assigned_to": test_user.id,
            "mark_pending": True,
            "pending_materials_note": "Missing invoices",
        },
    )
    assert response.status_code == 201
    item_id = response.json()["id"]

    patch = client.patch(
        f"/api/v1/vat/work-items/{item_id}",
        headers=advisor_headers,
        json={"assigned_to": None},
    )

    assert patch.status_code == 200
    body = patch.json()
    assert body["assigned_to"] is None
    assert body["pending_materials_note"] == "Missing invoices"


def test_patch_missing_item_returns_404(client, advisor_headers):
    response = client.patch(
        "/api/v1/vat/work-items/999999",
        headers=advisor_headers,
        json={"pending_materials_note": "new note"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VAT.NOT_FOUND"


def test_patch_filed_item_is_rejected(client, advisor_headers, vat_client, test_user):
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2026-02", assigned_to=test_user.id
    )
    _file_item(client, advisor_headers, item_id)

    response = client.patch(
        f"/api/v1/vat/work-items/{item_id}",
        headers=advisor_headers,
        json={"pending_materials_note": "late note"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAT.FILED_IMMUTABLE"


def test_delete_existing_non_filed_item_soft_deletes_and_hides_it(
    client, test_db, advisor_headers, vat_client, test_user
):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-03")

    response = client.delete(f"/api/v1/vat/work-items/{item_id}", headers=advisor_headers)

    assert response.status_code == 204
    item = test_db.get(VatWorkItem, item_id)
    assert item.deleted_at is not None
    assert item.deleted_by == test_user.id
    assert item.updated_at is not None

    global_list = client.get("/api/v1/vat/work-items", headers=advisor_headers)
    assert global_list.status_code == 200
    assert all(row["id"] != item_id for row in global_list.json()["items"])

    client_list = client.get(
        f"/api/v1/vat/clients/{vat_client.id}/work-items",
        headers=advisor_headers,
    )
    assert client_list.status_code == 200
    assert all(row["id"] != item_id for row in client_list.json()["items"])

    summary = client.get(f"/api/v1/vat/clients/{vat_client.id}/summary", headers=advisor_headers)
    assert summary.status_code == 200
    assert all(row["work_item_id"] != item_id for row in summary.json()["periods"])

    lookup = client.get(
        f"/api/v1/vat/work-items/lookup?client_record_id={vat_client.id}&period=2026-03",
        headers=advisor_headers,
    )
    assert lookup.status_code == 200
    assert lookup.json() is None

    detail = client.get(f"/api/v1/vat/work-items/{item_id}", headers=advisor_headers)
    assert detail.status_code == 404

    assert ACTION_VAT_WORK_ITEM_DELETED in _audit_actions(test_db, item_id)


def test_delete_missing_item_returns_404(client, advisor_headers):
    response = client.delete("/api/v1/vat/work-items/999999", headers=advisor_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VAT.NOT_FOUND"


def test_delete_filed_item_is_rejected(client, advisor_headers, vat_client, test_user):
    item_id = setup_ready_item(
        client, advisor_headers, vat_client, "2026-04", assigned_to=test_user.id
    )
    _file_item(client, advisor_headers, item_id)

    response = client.delete(f"/api/v1/vat/work-items/{item_id}", headers=advisor_headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VAT.FILED_IMMUTABLE"


def test_patch_writes_audit_for_changed_fields(client, test_db, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-05")

    response = client.patch(
        f"/api/v1/vat/work-items/{item_id}",
        headers=advisor_headers,
        json={"pending_materials_note": "Follow up"},
    )

    assert response.status_code == 200
    assert ACTION_VAT_WORK_ITEM_UPDATED in _audit_actions(test_db, item_id)
