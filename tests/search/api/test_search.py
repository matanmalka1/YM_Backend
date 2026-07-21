def test_search_requires_auth(client):
    response = client.get("/api/v1/search?search=x")
    assert response.status_code == 401


def test_search_items_requires_auth(client):
    response = client.get("/api/v1/search/items?search=x&result_type=task")
    assert response.status_code == 401


def test_search_rejects_a_missing_term(client, advisor_headers):
    response = client.get("/api/v1/search", headers=advisor_headers)
    assert response.status_code == 422


def test_search_rejects_a_whitespace_only_term(client, advisor_headers):
    """Whitespace is not a search: stripped first, then min_length fails."""
    response = client.get("/api/v1/search?search=%20%20", headers=advisor_headers)
    assert response.status_code == 422


def test_search_items_rejects_client_as_a_result_type(client, advisor_headers):
    """A client is a resolution result, not a record row — it must not be requestable."""
    response = client.get(
        "/api/v1/search/items?search=x&result_type=client",
        headers=advisor_headers,
    )
    assert response.status_code == 422


def test_no_match_returns_the_full_empty_envelope(client, advisor_headers):
    response = client.get("/api/v1/search?search=nothing-matches-this", headers=advisor_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["clients"] == {"items": [], "page": 1, "page_size": 20, "total": 0}
    assert data["matches"]["tasks"] == {"items": [], "total": 0}
    assert "items" not in data


def test_search_openapi_carries_only_the_term_and_pagination(client):
    """The seven deleted filter params must be gone from the contract, not just unused."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    search_params = {
        param["name"] for param in spec["paths"]["/api/v1/search"]["get"]["parameters"]
    }
    assert search_params == {"search", "page", "page_size"}

    items_params = {
        param["name"] for param in spec["paths"]["/api/v1/search/items"]["get"]["parameters"]
    }
    assert items_params == {"search", "result_type", "page", "page_size"}
