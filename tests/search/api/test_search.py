def test_search_endpoint(client, advisor_headers):
    """An empty search returns the two-phase envelope with nothing resolved."""
    response = client.get("/api/v1/search", headers=advisor_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["clients"]["items"] == []
    assert data["clients"]["total"] == 0
    assert data["items"]["tasks"] == {"items": [], "total": 0}


def test_search_requires_auth(client):
    """Test search requires authentication."""
    response = client.get("/api/v1/search")
    assert response.status_code == 401


def test_search_items_requires_auth(client):
    response = client.get("/api/v1/search/items?client_record_id=1&result_type=task")
    assert response.status_code == 401


def test_search_items_rejects_client_as_a_result_type(client, advisor_headers):
    """`client` is the feed's subject, not a row type — it must not be requestable."""
    response = client.get(
        "/api/v1/search/items?client_record_id=1&result_type=client",
        headers=advisor_headers,
    )
    assert response.status_code == 422


def test_search_openapi_uses_search_and_client_record_id_params(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/api/v1/search"]["get"]
    param_names = {param["name"] for param in operation["parameters"]}
    assert "search" in param_names
    assert "client_record_id" in param_names
    assert "client_id" not in param_names
    assert "query" not in param_names
    assert "client_name" not in param_names
    assert "client_search" not in param_names
