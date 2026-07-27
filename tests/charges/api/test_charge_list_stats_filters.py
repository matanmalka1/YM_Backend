def test_charge_list_stats_respect_business_id_filter(
    client, advisor_headers, create_client_with_business
):
    _client_a, biz_a = create_client_with_business(full_name="StatsAPI BizA", id_number="SA001")
    _client_b, biz_b = create_client_with_business(full_name="StatsAPI BizB", id_number="SA002")

    client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": biz_a.client_id,
            "business_id": biz_a.id,
            "amount": 100.0,
            "charge_type": "consultation_fee",
        },
    )
    client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": biz_b.client_id,
            "business_id": biz_b.id,
            "amount": 900.0,
            "charge_type": "consultation_fee",
        },
    )

    resp = client.get(
        f"/api/v1/charges?business_id={biz_a.id}",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["stats"]["draft"]["count"] == 1
    assert float(data["stats"]["draft"]["amount"]) == 100.0
    assert data["stats"]["paid"]["count"] == 0


def test_charge_list_stats_respect_period_filter(
    client, advisor_headers, create_client_with_business
):
    _client, biz = create_client_with_business(full_name="StatsAPI Period", id_number="SP001")

    client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": biz.client_id,
            "business_id": biz.id,
            "amount": 200.0,
            "charge_type": "monthly_retainer",
            "period": "2026-03",
        },
    )
    client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": biz.client_id,
            "business_id": biz.id,
            "amount": 300.0,
            "charge_type": "monthly_retainer",
            "period": "2026-04",
        },
    )

    resp = client.get(
        "/api/v1/charges?period=2026-03",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 1
    assert data["stats"]["draft"]["count"] == 1
    assert float(data["stats"]["draft"]["amount"]) == 200.0
