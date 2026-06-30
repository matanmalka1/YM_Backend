from app.users.models.user import User, UserRole
from tests.factories import create_user


def _create_managed_user(test_db) -> User:
    user = create_user(
        test_db,
        full_name="Managed User",
        email="managed.user@example.com",
        password="password123",
        role=UserRole.SECRETARY,
        is_active=True,
        commit=True,
    )
    return user


def _login(client, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_password_reset_invalidates_old_token(client, advisor_headers, test_db):
    user = _create_managed_user(test_db)
    old_token = _login(client, user.email, "password123")

    reset_response = client.post(
        f"/api/v1/users/{user.id}/reset-password",
        headers=advisor_headers,
        json={"new_password": "Newpassword123!"},
    )
    assert reset_response.status_code == 200

    protected_response = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert protected_response.status_code == 401


def test_deactivate_then_activate_does_not_restore_old_token(client, advisor_headers, test_db):
    user = _create_managed_user(test_db)
    old_token = _login(client, user.email, "password123")

    deactivate_response = client.post(
        f"/api/v1/users/{user.id}/deactivate",
        headers=advisor_headers,
    )
    assert deactivate_response.status_code == 200

    activate_response = client.post(
        f"/api/v1/users/{user.id}/activate",
        headers=advisor_headers,
    )
    assert activate_response.status_code == 200

    protected_response = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert protected_response.status_code == 401
