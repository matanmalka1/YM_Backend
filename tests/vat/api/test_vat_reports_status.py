from tests.vat.api.test_vat_reports_utils import (
    add_income_invoice,
    create_work_item,
)


class TestStatusTransitions:
    def _setup_item_with_invoice(self, client, headers, vat_client, period):
        item_id = create_work_item(client, headers, vat_client, period)
        add_income_invoice(client, headers, item_id)
        return item_id

    def test_mark_ready_for_review(self, client, advisor_headers, vat_client):
        item_id = self._setup_item_with_invoice(client, advisor_headers, vat_client, "2026-11")
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/ready-for-review",
            headers=advisor_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ready_for_review"

    def test_send_back_requires_advisor(self, client, secretary_headers, vat_client):
        response = client.post(
            "/api/v1/vat/work-items/1/send-back",
            headers=secretary_headers,
            json={"correction_note": "Please fix invoice 2"},
        )
        assert response.status_code == 403

    def test_send_back_success_as_advisor(self, client, advisor_headers, vat_client):
        item_id = self._setup_item_with_invoice(client, advisor_headers, vat_client, "2026-10")
        ready = client.post(
            f"/api/v1/vat/work-items/{item_id}/ready-for-review",
            headers=advisor_headers,
        )
        assert ready.status_code == 200

        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/send-back",
            headers=advisor_headers,
            json={"correction_note": "Missing receipt"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "data_entry_in_progress"
