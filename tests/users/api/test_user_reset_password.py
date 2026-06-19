from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService


def _make_user(test_db, email: str, role: UserRole = UserRole.SECRETARY) -> User:
    user = User(
        full_name="Reset Target",
        email=email,
        password_hash=AuthService.hash_password("password123"),
        role=role,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_reset_password_endpoint_success(client, test_db, advisor_headers):
    target = _make_user(test_db, "reset.endpoint@example.com")

    response = client.post(
        f"/api/v1/users/{target.id}/reset-password",
        headers=advisor_headers,
        json={"new_password": "Newpassword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == target.id
    assert "token_version" not in data


def test_reset_password_endpoint_returns_404_for_missing_user(client, advisor_headers):
    response = client.post(
        "/api/v1/users/999999/reset-password",
        headers=advisor_headers,
        json={"new_password": "Newpassword123!"},
    )

    assert response.status_code == 404
