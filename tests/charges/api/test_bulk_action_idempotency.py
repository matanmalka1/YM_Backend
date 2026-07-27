def test_bulk_action_missing_idempotency_key_returns_422(
    client, advisor_headers, create_client_with_business
):
    _client, biz = create_client_with_business(full_name="Idem Biz", id_number="IB001")
    charge = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": biz.client_id,
            "business_id": biz.id,
            "amount": 50.0,
            "charge_type": "consultation_fee",
        },
    )
    assert charge.status_code == 201

    resp = client.post(
        "/api/v1/charges/bulk-action",
        headers=advisor_headers,
        json={"charge_ids": [charge.json()["id"]], "action": "issue"},
    )
    assert resp.status_code == 422


def test_bulk_action_openapi_marks_idempotency_key_required(client, advisor_headers):
    schema = client.get("/openapi.json").json()
    bulk_op = schema["paths"]["/api/v1/charges/bulk-action"]["post"]
    params = bulk_op.get("parameters", [])
    idem_param = next(
        (p for p in params if p.get("name") == "X-Idempotency-Key"),
        None,
    )
    assert idem_param is not None, "X-Idempotency-Key parameter missing from OpenAPI"
    assert idem_param.get("required") is True, "X-Idempotency-Key must be required in OpenAPI"
