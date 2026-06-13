from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction
from app.users.services.auth_service import AuthService


def _create_target_user(test_db) -> User:
    user = User(
        full_name="Audit Target",
        email="audit.target@example.com",
        password_hash=AuthService.hash_password("password123"),
        role=UserRole.SECRETARY,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_login_events_are_persisted_in_audit_log(client, advisor_headers):
    success_response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert success_response.status_code == 200

    failed_response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert failed_response.status_code == 401

    logs_response = client.get("/api/v1/users/audit-logs", headers=advisor_headers)
    assert logs_response.status_code == 200
    actions = [item["action"] for item in logs_response.json()["items"]]
    assert AuditAction.LOGIN_SUCCESS.value in actions
    assert AuditAction.LOGIN_FAILURE.value in actions


def test_user_actions_are_persisted_in_audit_log(client, advisor_headers, test_db):
    target = _create_target_user(test_db)

    update_response = client.patch(
        f"/api/v1/users/{target.id}",
        headers=advisor_headers,
        json={"full_name": "Changed Name"},
    )
    assert update_response.status_code == 200

    deactivate_response = client.post(
        f"/api/v1/users/{target.id}/deactivate",
        headers=advisor_headers,
    )
    assert deactivate_response.status_code == 200

    reset_response = client.post(
        f"/api/v1/users/{target.id}/reset-password",
        headers=advisor_headers,
        json={"new_password": "Newpassword123!"},
    )
    assert reset_response.status_code == 200

    logs_response = client.get(
        "/api/v1/users/audit-logs",
        headers=advisor_headers,
        params={"target_user_id": target.id},
    )
    assert logs_response.status_code == 200
    actions = [item["action"] for item in logs_response.json()["items"]]
    assert AuditAction.USER_UPDATED.value in actions
    assert AuditAction.USER_DEACTIVATED.value in actions
    assert AuditAction.PASSWORD_RESET.value in actions


def test_audit_logs_openapi_uses_created_range_params(client, advisor_headers):
    schema = client.get("/openapi.json", headers=advisor_headers).json()
    params = {
        param["name"]
        for param in schema["paths"]["/api/v1/users/audit-logs"]["get"]["parameters"]
        if param["in"] == "query"
    }
    assert "created_after" in params
    assert "created_before" in params
    assert "from" not in params
    assert "to" not in params
