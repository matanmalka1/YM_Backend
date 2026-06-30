"""VAT audit reads now flow through the generic audit endpoint
``GET /api/v1/audit/{entity_type}/{entity_id}`` (the per-domain
``/vat/work-items/{id}/audit`` route was removed in the Phase 3 audit refactor).
Work-item lifecycle events live on ``vat_work_item``; invoice events on
``vat_invoice``."""

from tests.vat.api.test_vat_reports_utils import (
    add_income_invoice,
    create_work_item,
)


class TestWorkItemAuditTrail:
    def test_audit_trail_populated(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2025-04")

        resp = client.get(
            f"/api/v1/audit/vat_work_item/{item_id}",
            headers=advisor_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload["items"]) >= 1
        assert payload["total"] >= len(payload["items"])
        assert payload["entity_deleted"] is False
        first = payload["items"][0]
        assert first["entity_type"] == "vat_work_item"
        assert first["entity_id"] == item_id
        assert first["action"] == "vat_work_item.created"
        assert first["metadata_json"]["client_record_id"] == vat_client.id
        # user actor: performed_by populated; display preferred from snapshot.
        assert first["actor_type"] == "user"
        assert first["performed_by"] is not None

    def test_secretary_can_read_work_item_audit(
        self, client, advisor_headers, secretary_headers, vat_client
    ):
        item_id = create_work_item(client, advisor_headers, vat_client, "2025-09")

        resp = client.get(
            f"/api/v1/audit/vat_work_item/{item_id}",
            headers=secretary_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_audit_trail_is_paginated(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2025-05")
        # Adding the first invoice auto-advances the work item status -> a second
        # vat_work_item row (created + status_changed) on this entity's trail.
        add_income_invoice(client, advisor_headers, item_id)

        page_one = client.get(
            f"/api/v1/audit/vat_work_item/{item_id}?page=1&page_size=1",
            headers=advisor_headers,
        )
        assert page_one.status_code == 200
        first_payload = page_one.json()
        assert first_payload["page"] == 1
        assert first_payload["page_size"] == 1
        assert len(first_payload["items"]) == 1
        assert first_payload["total"] >= 2

        page_two = client.get(
            f"/api/v1/audit/vat_work_item/{item_id}?page=2&page_size=1",
            headers=advisor_headers,
        )
        assert page_two.status_code == 200
        second_payload = page_two.json()
        assert second_payload["page"] == 2
        assert len(second_payload["items"]) == 1
        assert second_payload["items"][0]["id"] != first_payload["items"][0]["id"]

    def test_audit_trail_returns_404_for_missing_item(self, client, advisor_headers):
        resp = client.get(
            "/api/v1/audit/vat_work_item/999999",
            headers=advisor_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "AUDIT.ENTITY_NOT_FOUND"


class TestInvoiceAuditTrail:
    def test_invoice_creation_audited_on_vat_invoice_entity(
        self, client, advisor_headers, vat_client
    ):
        item_id = create_work_item(client, advisor_headers, vat_client, "2025-06")
        invoice = add_income_invoice(client, advisor_headers, item_id)
        invoice_id = invoice["id"]

        resp = client.get(
            f"/api/v1/audit/vat_invoice/{invoice_id}",
            headers=advisor_headers,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] >= 1
        first = payload["items"][0]
        assert first["entity_type"] == "vat_invoice"
        assert first["action"] == "vat_invoice.created"
        assert first["metadata_json"]["client_record_id"] == vat_client.id
        assert first["metadata_json"]["vat_work_item_id"] == item_id
        assert first["new_value"]["invoice_id"] == invoice_id
