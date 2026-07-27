from tests.clients.helpers import create_client_via_api
from tests.helpers.identity import seed_client_identity


def test_get_and_patch_client(client, advisor_headers):
    created = create_client_via_api(
        client, advisor_headers, full_name="Client A", id_number="700000011"
    )
    client_id = created.json()["client"]["id"]

    fetched = client.get(f"/api/v1/clients/{client_id}", headers=advisor_headers)
    assert fetched.status_code == 200
    assert fetched.json()["full_name"] == "Client A"

    updated = client.patch(
        f"/api/v1/clients/{client_id}",
        headers=advisor_headers,
        json={"full_name": "Client B", "phone": "0501234567"},
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Client B"
    assert updated.json()["phone"] == "0501234567"


def test_get_client_not_found_returns_domain_error(client, advisor_headers):
    response = client.get("/api/v1/clients/99999", headers=advisor_headers)

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "CLIENT_RECORD.NOT_FOUND"


def test_delete_and_restore_client_role_rules(client, advisor_headers, secretary_headers):
    created = create_client_via_api(client, advisor_headers, id_number="700000029")
    client_id = created.json()["client"]["id"]

    denied = client.delete(f"/api/v1/clients/{client_id}", headers=secretary_headers)
    assert denied.status_code == 403

    deleted = client.delete(f"/api/v1/clients/{client_id}", headers=advisor_headers)
    assert deleted.status_code == 204

    fetched_after_delete = client.get(f"/api/v1/clients/{client_id}", headers=advisor_headers)
    assert fetched_after_delete.status_code == 404

    restore_denied = client.post(f"/api/v1/clients/{client_id}/restore", headers=secretary_headers)
    assert restore_denied.status_code == 403

    restored = client.post(f"/api/v1/clients/{client_id}/restore", headers=advisor_headers)
    assert restored.status_code == 200
    assert restored.json()["id"] == client_id


def test_restore_conflict_when_active_duplicate_exists(
    client, advisor_headers, test_db, actor_user
):
    first = create_client_via_api(
        client, advisor_headers, full_name="Old One", id_number="700000037"
    )
    first_id = first.json()["client"]["id"]

    client.delete(f"/api/v1/clients/{first_id}", headers=advisor_headers)
    seed_client_identity(
        test_db,
        full_name="Active One",
        id_number="700000037",
        created_by=actor_user.id,
    )

    restored = client.post(f"/api/v1/clients/{first_id}/restore", headers=advisor_headers)

    assert restored.status_code == 409
    assert restored.json()["error"]["code"] == "CLIENT.CONFLICT"


def test_create_returns_deleted_exists_conflict_payload(client, advisor_headers):
    first = create_client_via_api(
        client, advisor_headers, full_name="Deleted Source", id_number="700000045"
    )
    first_id = first.json()["client"]["id"]
    client.delete(f"/api/v1/clients/{first_id}", headers=advisor_headers)

    duplicate = create_client_via_api(
        client, advisor_headers, full_name="Try Again", id_number="700000045"
    )

    assert duplicate.status_code == 409
    payload = duplicate.json()["error"]
    assert payload["code"] == "CLIENT.DELETED_EXISTS"
    assert payload["details"]["conflict"]["id_number"] == "700000045"
    assert len(payload["details"]["conflict"]["deleted_clients"]) == 1


def test_conflict_endpoint_includes_active_and_deleted(client, advisor_headers):
    _active = create_client_via_api(
        client, advisor_headers, full_name="Conflict Active", id_number="700000052"
    )
    deleted = create_client_via_api(
        client, advisor_headers, full_name="Conflict Deleted", id_number="700000060"
    )

    client.delete(f"/api/v1/clients/{deleted.json()['client']['id']}", headers=advisor_headers)

    active_info = client.get("/api/v1/clients/conflict/700000052", headers=advisor_headers)
    assert active_info.status_code == 200
    body_active = active_info.json()
    assert len(body_active["active_clients"]) == 1
    assert len(body_active["deleted_clients"]) == 0

    deleted_info = client.get("/api/v1/clients/conflict/700000060", headers=advisor_headers)
    assert deleted_info.status_code == 200
    body_deleted = deleted_info.json()
    assert len(body_deleted["active_clients"]) == 0
    assert len(body_deleted["deleted_clients"]) == 1


def test_create_conflict_payload_contains_conflict_lists(client, advisor_headers):
    create_client_via_api(client, advisor_headers, full_name="First", id_number="700000078")

    duplicate = create_client_via_api(
        client, advisor_headers, full_name="Second", id_number="700000078"
    )

    assert duplicate.status_code == 409
    payload = duplicate.json()["error"]
    assert payload["code"] == "CLIENT.CONFLICT"
    assert payload["details"]["conflict"]["id_number"] == "700000078"
    assert len(payload["details"]["conflict"]["active_clients"]) == 1


def test_create_validates_israeli_checksum_for_individual(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Checksum Invalid",
                "id_number": "123456789",
                "id_number_type": "individual",
                "entity_type": "osek_murshe",
                "phone": "050-1234567",
                "email": "checksum@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "vat_reporting_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {
                "business_name": "Checksum Invalid Business",
                "opened_at": "2026-04-19",
            },
        },
    )

    assert response.status_code == 422


def test_create_validates_israeli_checksum_for_corporation(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Bad Corp",
                "id_number": "700000001",
                "id_number_type": "corporation",
                "entity_type": "company_ltd",
                "phone": "050-1234567",
                "email": "badcorp@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "vat_reporting_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {
                "business_name": "Bad Corp Business",
                "opened_at": "2026-04-19",
            },
        },
    )

    assert response.status_code == 422


def test_create_rejects_manual_vat_frequency_for_osek_patur(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Exempt Client",
                "id_number": "039337423",
                "entity_type": "osek_patur",
                "phone": "050-1234567",
                "email": "exempt@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "vat_reporting_frequency": "exempt",
                "accountant_id": 1,
            },
            "business": {"business_name": "Exempt Business"},
        },
    )

    assert response.status_code == 422


def test_create_rejects_manual_vat_exempt_ceiling(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Ceiling Client",
                "id_number": "039337423",
                "entity_type": "osek_patur",
                "phone": "050-1234567",
                "email": "ceiling@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "vat_exempt_ceiling": "120000",
                "accountant_id": 1,
            },
            "business": {"business_name": "Ceiling Business"},
        },
    )

    assert response.status_code == 422


def test_create_rejects_unsupported_employee(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Employee Client",
                "id_number": "039337423",
                "entity_type": "employee",
                "phone": "050-1234567",
                "email": "employee@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "accountant_id": 1,
            },
            "business": {"business_name": "Employee Business"},
        },
    )

    assert response.status_code == 422


def test_create_rejects_missing_company_business_name(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Company Client",
                "id_number": "039337423",
                "entity_type": "company_ltd",
                "phone": "050-1234567",
                "email": "company@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "vat_reporting_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {"business_name": "", "opened_at": None},
        },
    )

    assert response.status_code == 422
    errors = response.json()["error"]["details"]
    assert any("יש להזין שם עסק" in error["message"] for error in errors)


def test_update_rejects_manual_vat_exempt_ceiling_payload(client, advisor_headers):
    created = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Editable Ceiling",
                "id_number": "039337423",
                "entity_type": "osek_patur",
                "phone": "050-1234567",
                "email": "editable@example.com",
                "address_street": "Main",
                "address_building_number": "10",
                "address_apartment": "5",
                "address_city": "Tel Aviv",
                "address_zip_code": "1234567",
                "advance_payment_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {"business_name": "Editable Ceiling Business"},
        },
    )
    assert created.status_code == 201
    client_id = created.json()["client"]["id"]

    response = client.patch(
        f"/api/v1/clients/{client_id}",
        headers=advisor_headers,
        json={"vat_exempt_ceiling": "130000"},
    )

    assert response.status_code == 422
    errors = response.json()["error"]["details"]
    assert any(
        'תקרת פטור מע"מ נקבעת על ידי המערכת ואינה ניתנת לעריכה ידנית' in error["message"]
        for error in errors
    )


def test_list_clients_respects_search_and_pagination(client, advisor_headers):
    create_client_via_api(client, advisor_headers, full_name="Alpha Client", id_number="700000086")
    create_client_via_api(client, advisor_headers, full_name="Beta Client", id_number="700000094")

    response = client.get(
        "/api/v1/clients?search=Alpha&page=1&page_size=1",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["full_name"] == "Alpha Client"


def test_list_sidebar_clients_returns_lightweight_payload(client, advisor_headers):
    create_client_via_api(
        client,
        advisor_headers,
        full_name="Sidebar Alpha",
        id_number="700000086",
        phone="0501111111",
        email="sidebar@example.com",
    )
    create_client_via_api(client, advisor_headers, full_name="Sidebar Beta", id_number="700000094")

    response = client.get(
        "/api/v1/clients/sidebar?search=Alpha&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item == {
        "id": item["id"],
        "full_name": "Sidebar Alpha",
        "office_client_number": item["office_client_number"],
        "phone": "0501111111",
        "email": "sidebar@example.com",
        "entity_type": "company_ltd",
        "vat_reporting_frequency": "monthly",
    }
    assert "annual_turnover" not in item
    assert "active_binder_number" not in item
    assert "stats" not in data
