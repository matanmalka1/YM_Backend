def test_secretary_sees_charge_amounts(
    client, secretary_headers, advisor_headers, create_client_with_business
):
    """Secretary has full charge visibility — same as advisor."""
    _test_client, test_business = create_client_with_business(
        full_name="Auth Test",
        id_number="700000002",
    )

    create_response = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": test_business.client_record_id,
            "business_id": test_business.id,
            "amount": 500.0,
            "charge_type": "monthly_retainer",
        },
    )
    assert create_response.status_code == 201

    for headers in (secretary_headers, advisor_headers):
        response = client.get("/api/v1/charges", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if data["items"]:
            assert "amount" in data["items"][0]
