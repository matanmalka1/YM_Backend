from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from app.users.models.user import UserRole
from app.users.services.user_token_service import generate_access_token


def test_users_endpoint_requires_token(client):
    response = client.get("/api/v1/users")
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "חסר טוקן אימות"


def test_users_endpoint_rejects_invalid_and_malformed_tokens(client):
    invalid_response = client.get(
        "/api/v1/users",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert invalid_response.status_code == 401
    assert invalid_response.json()["error"]["message"] == "הטוקן אינו תקין או שפג תוקפו"

    now = datetime.now(UTC)
    malformed_token = jwt.encode(
        {
            "sub": "not-an-int",
            "email": "malformed@example.com",
            "role": "advisor",
            "iat": now,
            "exp": now + timedelta(hours=1),
            "tv": "x",
            "type": "access",
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    malformed_response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {malformed_token}"},
    )
    assert malformed_response.status_code == 401
    assert malformed_response.json()["error"]["message"] == "פורמט הטוקן אינו תקין"


def test_inactive_user_token_is_rejected(client, test_db, user_factory):
    user = user_factory(
        full_name="Inactive Auth User",
        email="inactive.token@example.com",
        password="password123",
        role=UserRole.ADVISOR,
        is_active=False,
        commit=True,
    )

    token = generate_access_token(user)
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "המשתמש לא נמצא או שאינו פעיל"


def test_access_cookie_does_not_authenticate_without_authorization_header(client, auth_token):
    client.cookies.set("access_token", auth_token)
    response = client.get("/api/v1/users")
    assert response.status_code == 401
