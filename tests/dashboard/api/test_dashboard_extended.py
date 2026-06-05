def test_overview_returns_attention_field(client, advisor_headers):
    """Dashboard overview response includes attention contract field."""
    response = client.get("/api/v1/dashboard/overview", headers=advisor_headers)

    assert response.status_code == 200
    data = response.json()
    assert "attention" in data
    assert isinstance(data["attention"]["items"], list)
