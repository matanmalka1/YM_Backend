def create_work_item(client, headers, vat_client, period, assigned_to: int | None = None):
    body = {"client_record_id": vat_client.id, "period": period}
    if assigned_to is not None:
        body["assigned_to"] = assigned_to
    response = client.post(
        "/api/v1/vat/work-items",
        headers=headers,
        json=body,
    )
    assert response.status_code == 201
    return response.json()["id"]


def income_payload(
    invoice_number="INV-001",
    invoice_date="2026-01-15T00:00:00",
    counterparty_name="Customer A",
    gross_amount="1180.00",
):
    payload = {
        "invoice_type": "income",
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "counterparty_name": counterparty_name,
        "gross_amount": gross_amount,
    }
    return payload


def add_income_invoice(client, headers, item_id, payload=None):
    response = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=headers,
        json=payload or income_payload(),
    )
    assert response.status_code == 201
    return response.json()


def setup_ready_item(client, headers, vat_client, period, assigned_to: int | None = None):
    item_id = create_work_item(client, headers, vat_client, period, assigned_to=assigned_to)
    add_income_invoice(client, headers, item_id)
    client.post(f"/api/v1/vat/work-items/{item_id}/ready-for-review", headers=headers)
    return item_id
