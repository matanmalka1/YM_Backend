def test_root_and_info_routes_return_expected_payload(client):
    root = client.get("/")
    info = client.get("/info")

    assert root.status_code == 200
    assert root.json() == {"service": "YM-Tax-CRM", "status": "running"}
    assert info.status_code == 200
    assert info.json() == {"app": "YM Tax CRM", "env": "test"}
