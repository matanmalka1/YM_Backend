from app.users.models.user import User, UserRole
from tests.factories import create_user


def _create_user(test_db, email: str = "logout.test@example.com") -> User:
    user = create_user(
        test_db,
        full_name="Logout Test User",
        email=email,
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


def test_logout_invalidates_bearer_token(client, test_db):
    """Bearer token must be rejected after logout, before JWT expiry."""
    user = _create_user(test_db)
    token = _login(client, user.email, "password123")

    # Confirm token works before logout
    pre_logout = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pre_logout.status_code == 200

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204

    # Same token must now be rejected
    post_logout = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert post_logout.status_code == 401


def test_logout_requires_bearer_token(client):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401


def test_logout_is_audited(client, advisor_headers, test_db):
    """Logout action must appear in the audit log."""
    from app.users.models.user_audit_log import AuditAction

    user = _create_user(test_db, email="logout.audit@example.com")
    token = _login(client, user.email, "password123")

    client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )

    logs_response = client.get("/api/v1/users/audit-logs", headers=advisor_headers)
    assert logs_response.status_code == 200
    actions = [item["action"] for item in logs_response.json()["items"]]
    assert AuditAction.LOGOUT.value in actions


def test_new_login_after_logout_works(client, test_db):
    """After logout, the user can log in again and receive a valid new token."""
    user = _create_user(test_db, email="logout.relogin@example.com")
    old_token = _login(client, user.email, "password123")

    client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {old_token}"},
    )

    new_token = _login(client, user.email, "password123")
    assert new_token != old_token

    response = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert response.status_code == 200
