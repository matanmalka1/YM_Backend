def test_search_endpoint(client, advisor_headers):
    """Test search endpoint."""
    response = client.get("/api/v1/search", headers=advisor_headers)

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "total" in data


def test_search_requires_auth(client):
    """Test search requires authentication."""
    response = client.get("/api/v1/search")
    assert response.status_code == 401
