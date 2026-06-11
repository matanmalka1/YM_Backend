from tests.vat.api.test_vat_reports_utils import (
    add_income_invoice,
    create_work_item,
)


class TestAuditTrail:
    def test_audit_trail_populated(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2025-04")

        resp = client.get(
            f"/api/v1/vat/work-items/{item_id}/audit",
            headers=advisor_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload["items"]) >= 1
        assert payload["total"] >= len(payload["items"])
        first = payload["items"][0]
        assert first["work_item_id"] == item_id
        assert first["action"] == "material_received"
        assert first["performed_by_name"] is not None

    def test_audit_trail_is_paginated(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2025-05")
        add_income_invoice(client, advisor_headers, item_id)

        page_one = client.get(
            f"/api/v1/vat/work-items/{item_id}/audit?page=1&page_size=1",
            headers=advisor_headers,
        )
        assert page_one.status_code == 200
        first_payload = page_one.json()
        assert first_payload["page"] == 1
        assert first_payload["page_size"] == 1
        assert len(first_payload["items"]) == 1
        assert first_payload["total"] >= 2

        page_two = client.get(
            f"/api/v1/vat/work-items/{item_id}/audit?page=2&page_size=1",
            headers=advisor_headers,
        )
        assert page_two.status_code == 200
        second_payload = page_two.json()
        assert second_payload["page"] == 2
        assert len(second_payload["items"]) == 1
        # Pages must not overlap.
        assert second_payload["items"][0]["id"] != first_payload["items"][0]["id"]

    def test_audit_trail_returns_404_for_missing_item(self, client, advisor_headers):
        resp = client.get(
            "/api/v1/vat/work-items/999999/audit",
            headers=advisor_headers,
        )
        assert resp.status_code == 404
        payload = resp.json()
        assert payload["error"]["code"] == "VAT.NOT_FOUND"
