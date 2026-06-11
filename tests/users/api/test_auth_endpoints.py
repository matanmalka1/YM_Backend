from app.config import settings


def _login(client, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {
        "access_token": response.json()["access_token"],
        "set_cookie": response.headers["set-cookie"],
    }


def test_login_sets_refresh_cookie_ttl(client, test_user):
    set_cookie = _login(client, test_user.email, "password123")["set_cookie"]

    max_age = f"Max-Age={settings.AUTH_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60}"

    assert "refresh_token=" in set_cookie
    assert max_age in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie


def test_refresh_returns_new_access_token(client, test_user):
    _login(client, test_user.email, "password123")

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


def test_me_returns_current_user(client, test_user):
    login = _login(client, test_user.email, "password123")

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == test_user.id
    assert response.json()["email"] == test_user.email


def test_logout_invalidates_old_token_and_clears_cookie(client, test_user):
    login = _login(client, test_user.email, "password123")
    token = login["access_token"]

    protected_before = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert protected_before.status_code == 200

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204
    assert "refresh_token=" in logout_response.headers["set-cookie"]

    protected_after = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert protected_after.status_code == 401
