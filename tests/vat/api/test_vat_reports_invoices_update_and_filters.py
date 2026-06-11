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


def _create_income_invoice(client, advisor_headers, vat_client, period, **kwargs):
    item_id = create_work_item(client, advisor_headers, vat_client, period)
    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(**kwargs),
    )
    assert resp.status_code == 201
    return item_id, resp.json()["id"]


def test_update_invoice_empty_patch_returns_422(client, advisor_headers, vat_client):
    item_id, invoice_id = _create_income_invoice(
        client, advisor_headers, vat_client, "2026-03", invoice_number="INV-EMPTY"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={},
    )
    assert resp.status_code == 422


def test_update_invoice_unknown_field_returns_422(client, advisor_headers, vat_client):
    item_id, invoice_id = _create_income_invoice(
        client, advisor_headers, vat_client, "2026-03", invoice_number="INV-UNK"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"definitely_not_a_field": 1},
    )
    assert resp.status_code == 422


def test_update_invoice_null_on_non_nullable_returns_422(client, advisor_headers, vat_client):
    item_id, invoice_id = _create_income_invoice(
        client, advisor_headers, vat_client, "2026-03", invoice_number="INV-NULL"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"invoice_number": None},
    )
    assert resp.status_code == 422


def test_update_invoice_null_expense_category_rejected(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-03")
    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=_expense_payload(invoice_number="EXP-NULLCAT"),
    )
    assert resp.status_code == 201
    invoice_id = resp.json()["id"]

    patched = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"expense_category": None},
    )
    assert patched.status_code == 422


def test_update_invoice_null_clears_nullable_business_activity_id(
    client, advisor_headers, vat_client, test_db
):
    from app.businesses.repositories.business_repository import BusinessRepository
    from app.clients.repositories.client_record_repository import ClientRecordRepository

    item_id = create_work_item(client, advisor_headers, vat_client, "2026-03")
    record = ClientRecordRepository(test_db).get_by_id(vat_client.id)
    business = BusinessRepository(test_db).list_by_legal_entity(record.legal_entity_id)[0]

    create_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json={**income_payload(invoice_number="INV-BIZ"), "business_activity_id": business.id},
    )
    assert create_resp.status_code == 201
    invoice_id = create_resp.json()["id"]
    assert create_resp.json()["business_activity_id"] == business.id

    cleared = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"business_activity_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["business_activity_id"] is None


def test_update_invoice_single_field_leaves_financials_unchanged(
    client, advisor_headers, vat_client
):
    item_id, invoice_id = _create_income_invoice(
        client,
        advisor_headers,
        vat_client,
        "2026-03",
        invoice_number="INV-SIB",
        gross_amount="1180.00",
    )

    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"invoice_number": "INV-SIB-2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["invoice_number"] == "INV-SIB-2"
    # gross/rate untouched => net+vat unchanged.
    assert body["net_amount"] == "1000.00"
    assert body["vat_amount"] == "180.00"


def _create_invoice_with_counterparty(client, advisor_headers, vat_client, period):
    item_id = create_work_item(client, advisor_headers, vat_client, period)
    resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json={
            **income_payload(invoice_number="INV-CP"),
            "counterparty_id": "514274414",
            "counterparty_id_type": "il_business",
        },
    )
    assert resp.status_code == 201
    return item_id, resp.json()["id"]


def test_update_invoice_clearing_only_id_leaves_invalid_pair_rejected(
    client, advisor_headers, vat_client
):
    # Clearing counterparty_id while the persisted type stays il_business would
    # leave an invalid effective pair -> must be rejected, not silently applied.
    item_id, invoice_id = _create_invoice_with_counterparty(
        client, advisor_headers, vat_client, "2026-03"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"counterparty_id": None},
    )
    assert resp.status_code == 400


def test_update_invoice_clearing_only_type_is_allowed(client, advisor_headers, vat_client):
    # An id with no type is a permitted state (the counterparty rule only
    # constrains id when a *type* is present), so clearing just the type is OK.
    item_id, invoice_id = _create_invoice_with_counterparty(
        client, advisor_headers, vat_client, "2026-03"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"counterparty_id_type": None},
    )
    assert resp.status_code == 200
    assert resp.json()["counterparty_id_type"] is None
    assert resp.json()["counterparty_id"] == "514274414"


def test_update_invoice_clearing_both_sides_succeeds(client, advisor_headers, vat_client):
    item_id, invoice_id = _create_invoice_with_counterparty(
        client, advisor_headers, vat_client, "2026-03"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"counterparty_id": None, "counterparty_id_type": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["counterparty_id"] is None
    assert body["counterparty_id_type"] is None


def test_update_invoice_change_type_with_compatible_new_id_succeeds(
    client, advisor_headers, vat_client
):
    item_id, invoice_id = _create_invoice_with_counterparty(
        client, advisor_headers, vat_client, "2026-03"
    )
    resp = client.patch(
        f"/api/v1/vat/work-items/{item_id}/invoices/{invoice_id}",
        headers=advisor_headers,
        json={"counterparty_id_type": "anonymous", "counterparty_id": "999999999"},
    )
    assert resp.status_code == 200
    assert resp.json()["counterparty_id_type"] == "anonymous"


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
