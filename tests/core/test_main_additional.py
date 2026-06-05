def test_root_and_info_routes_return_expected_payload(client):
    root = client.get("/")
    info = client.get("/info")

    assert root.status_code == 200
    assert root.json() == {"service": "binder-billing-crm", "status": "running"}
    assert info.status_code == 200
    assert info.json() == {"app": "Binder Billing CRM", "env": "test"}
