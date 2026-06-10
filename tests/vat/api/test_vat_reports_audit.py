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

        resp = client.get(
            f"/api/v1/vat/work-items/{item_id}/audit?limit=1&offset=1",
            headers=advisor_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload["items"]) == 1
        assert payload["total"] >= 2
