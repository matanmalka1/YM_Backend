from tests.vat.api.test_vat_reports_utils import (
    create_work_item,
    income_payload,
)


def _expense_payload(
    invoice_number: str = "EXP-001",
    document_type: str = "receipt",
    counterparty_id: str | None = None,
):
    payload = {
        "invoice_type": "expense",
        "invoice_number": invoice_number,
        "invoice_date": "2026-01-15T00:00:00",
        "counterparty_name": "Supplier A",
        "gross_amount": "590.00",
        "expense_category": "office",
        "document_type": document_type,
    }
    if counterparty_id is not None:
        payload["counterparty_id"] = counterparty_id
    return payload


def test_update_invoice_patch_success(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-03")
    create_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-UPD-1", gross_amount="1180.00"),
    )
    assert create_resp.status_code == 201
    invoice_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={
            "gross_amount": "35400.00",
            "invoice_number": "INV-UPD-2",
        },
    )

    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["invoice_number"] == "INV-UPD-2"
    assert body["net_amount"] == "30000.00"
    assert body["vat_amount"] == "5400.00"
    assert body["is_exceptional"] is True


def test_update_invoice_patch_not_found_returns_404(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-04")

    patch_resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/999999",
        headers=advisor_headers,
        json={"invoice_number": "INV-MISSING"},
    )

    assert patch_resp.status_code == 404


def test_update_invoice_patch_invalid_amount_returns_422(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-05")
    create_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-422"),
    )
    assert create_resp.status_code == 201
    invoice_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"gross_amount": "0.00"},
    )

    assert patch_resp.status_code == 422


def test_list_invoices_filter_by_type(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-06")
    income_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-INC"),
    )
    expense_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=_expense_payload(invoice_number="INV-EXP"),
    )
    assert income_resp.status_code == 201
    assert expense_resp.status_code == 201

    list_resp = client.get(
        f"/api/v1/vat/work-items/{item_id}/invoices?invoice_type=income",
        headers=advisor_headers,
    )

    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["invoice_type"] == "income"


def test_expense_tax_invoice_requires_counterparty_id(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-07")

    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=_expense_payload(invoice_number="EXP-TAX", document_type="tax_invoice"),
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAT.COUNTERPARTY_ID_REQUIRED"


def test_create_invoice_persists_counterparty_identity_fields(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-08")

    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json={
            **_expense_payload(
                invoice_number="EXP-ID-1",
                document_type="tax_invoice",
                counterparty_id="512345679",
            ),
            "counterparty_id_type": "il_business",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["counterparty_id"] == "512345679"
    assert body["counterparty_id_type"] == "il_business"


def test_update_invoice_persists_counterparty_identity_fields(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-09")
    create_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-ID-UPD"),
    )
    assert create_resp.status_code == 201
    invoice_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={
            "counterparty_id": "123456782",
            "counterparty_id_type": "il_personal",
        },
    )

    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["counterparty_id"] == "123456782"
    assert body["counterparty_id_type"] == "il_personal"


def test_update_invoice_accepts_valid_personal_id_checksum(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-10")
    create_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-ID-CHECKSUM"),
    )
    assert create_resp.status_code == 201
    invoice_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={
            "counterparty_id": "100000009",
            "counterparty_id_type": "il_personal",
        },
    )

    assert patch_resp.status_code == 200
    assert patch_resp.json()["counterparty_id"] == "100000009"
