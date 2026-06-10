from tests.vat.api.test_vat_reports_utils import create_work_item


def test_materials_complete_transitions_pending_to_material_received(
    client, advisor_headers, vat_client
):
    create_resp = client.post(
        "/api/v1/vat/work-items",
        headers=advisor_headers,
        json={
            "client_record_id": vat_client.id,
            "period": "2026-12",
            "mark_pending": True,
            "pending_materials_note": "Missing statements",
        },
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "pending_materials"

    complete_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/materials-complete",
        headers=advisor_headers,
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "material_received"


def test_materials_complete_rejects_invalid_status(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2027-01")

    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/materials-complete",
        headers=advisor_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAT.INVALID_TRANSITION"
