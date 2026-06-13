from tests.vat.api.test_vat_reports_utils import (
    add_income_invoice,
    create_work_item,
    income_payload,
)


class TestInvoices:
    def test_add_income_invoice_201(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-05")
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=income_payload(),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["invoice_type"] == "income"
        assert data["vat_amount"] == "180.00"
        assert data["created_at"].endswith("Z")
        assert "T" in data["created_at"]

    def test_add_invoice_updates_totals(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-06")
        add_income_invoice(client, advisor_headers, item_id, income_payload("INV-001"))
        r = client.get(f"/api/v1/vat/work-items/{item_id}", headers=advisor_headers)
        data = r.json()
        assert float(data["total_output_vat"]) == 180.0
        assert data["status"] == "data_entry_in_progress"

    def test_negative_gross_rejected_422(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-07")
        payload = income_payload()
        payload["gross_amount"] = "-10.00"
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=payload,
        )
        assert response.status_code == 422

    def test_expense_without_category_400(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-08")
        payload = {
            "invoice_type": "expense",
            "invoice_number": "EXP-001",
            "invoice_date": "2026-01-15T00:00:00",
            "counterparty_name": "Supplier",
            "gross_amount": "590.00",
        }
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=payload,
        )
        assert response.status_code == 400

    def test_list_invoices(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-09")
        client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=income_payload("INV-001"),
        )
        client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=income_payload("INV-002"),
        )
        r = client.get(f"/api/v1/vat/work-items/{item_id}/invoices", headers=advisor_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert all(item["created_at"].endswith("Z") for item in items)
        assert all("T" in item["created_at"] for item in items)

    def test_delete_invoice(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-10")
        inv_r = client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=income_payload(),
        )
        invoice_id = inv_r.json()["id"]

        del_r = client.delete(
            f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
            headers=advisor_headers,
        )
        assert del_r.status_code == 204
