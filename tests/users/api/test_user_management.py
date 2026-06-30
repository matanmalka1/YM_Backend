from app.users.models.user import User, UserRole
from tests.factories import create_user


def _make_user(test_db, email: str, role: UserRole = UserRole.SECRETARY) -> User:
    user = create_user(
        test_db,
        full_name="Managed User",
        email=email,
        password="password123",
        role=role,
        is_active=True,
        commit=True,
    )
    return user


def test_advisor_can_create_list_and_get_users(client, advisor_headers):
    create_response = client.post(
        "/api/v1/users",
        headers=advisor_headers,
        json={
            "full_name": "New Secretary",
            "email": "new.secretary@example.com",
            "phone": "050-1234567",
            "role": "secretary",
            "password": "Password123!",
        },
    )
    assert create_response.status_code == 201
    created_id = create_response.json()["id"]

    list_response = client.get("/api/v1/users", headers=advisor_headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 2

    get_response = client.get(f"/api/v1/users/{created_id}", headers=advisor_headers)
    assert get_response.status_code == 200
    assert get_response.json()["email"] == "new.secretary@example.com"


def test_list_users_supports_is_active_filter(client, advisor_headers, test_db):
    active_user = _make_user(test_db, "active.only@example.com")
    inactive_user = _make_user(test_db, "inactive.only@example.com")
    inactive_user.is_active = False
    test_db.commit()

    all_response = client.get("/api/v1/users", headers=advisor_headers)
    assert all_response.status_code == 200
    all_ids = {item["id"] for item in all_response.json()["items"]}
    assert active_user.id in all_ids
    assert inactive_user.id in all_ids

    active_response = client.get("/api/v1/users?is_active=true", headers=advisor_headers)
    assert active_response.status_code == 200
    active_body = active_response.json()
    assert active_body["total"] >= 2
    assert all(item["is_active"] is True for item in active_body["items"])
    assert inactive_user.id not in {item["id"] for item in active_body["items"]}

    inactive_response = client.get("/api/v1/users?is_active=false", headers=advisor_headers)
    assert inactive_response.status_code == 200
    inactive_body = inactive_response.json()
    assert inactive_body["total"] == 1
    assert {item["id"] for item in inactive_body["items"]} == {inactive_user.id}
    assert all(item["is_active"] is False for item in inactive_body["items"])


def test_list_users_supports_search_filter(client, advisor_headers, test_db):
    name_match = _make_user(test_db, "dana.search@example.com")
    name_match.full_name = "Dana Search"
    email_match = _make_user(test_db, "mail.findme@example.com")
    email_match.full_name = "Other User"
    test_db.commit()

    name_response = client.get("/api/v1/users?search=Dana", headers=advisor_headers)
    assert name_response.status_code == 200
    name_body = name_response.json()
    assert name_body["total"] == 1
    assert [item["id"] for item in name_body["items"]] == [name_match.id]

    email_response = client.get("/api/v1/users?search=mail.findme", headers=advisor_headers)
    assert email_response.status_code == 200
    email_body = email_response.json()
    assert email_body["total"] == 1
    assert [item["id"] for item in email_body["items"]] == [email_match.id]


def test_secretary_cannot_access_user_management(client, secretary_headers):
    response = client.get("/api/v1/users", headers=secretary_headers)
    assert response.status_code == 403


def test_advisor_can_update_and_activate_deactivate_user(client, advisor_headers, test_db):
    target = _make_user(test_db, "target@example.com")

    update_response = client.patch(
        f"/api/v1/users/{target.id}",
        headers=advisor_headers,
        json={"full_name": "Renamed User", "role": "advisor"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["full_name"] == "Renamed User"
    assert update_response.json()["role"] == "advisor"

    deactivate_response = client.post(
        f"/api/v1/users/{target.id}/deactivate",
        headers=advisor_headers,
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    assert "token_version" not in deactivate_response.json()

    activate_response = client.post(
        f"/api/v1/users/{target.id}/activate",
        headers=advisor_headers,
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True


def test_can_update_email_field(client, advisor_headers, test_db):
    target = _make_user(test_db, "immutable@example.com")
    response = client.patch(
        f"/api/v1/users/{target.id}",
        headers=advisor_headers,
        json={"email": "new@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "new@example.com"


def test_cannot_deactivate_self(client, advisor_headers, test_user):
    response = client.post(f"/api/v1/users/{test_user.id}/deactivate", headers=advisor_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER.FORBIDDEN"
