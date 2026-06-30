import hashlib
from datetime import timedelta

from sqlalchemy import func, select

from app.users.models.user import User, UserRole
from app.users.models.user_password_reset_token import PasswordResetToken
from app.users.services.user_auth_service import AuthService
from app.utils.time_utils import utcnow
from tests.factories import create_user


def _create_user(test_db, *, email: str = "reset.self@example.com") -> User:
    user = create_user(
        test_db,
        full_name="Reset Self",
        email=email,
        password="password123",
        role=UserRole.SECRETARY,
        is_active=True,
        commit=True,
    )
    return user


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_forgot_password_returns_generic_message_and_stores_hashed_token(client, test_db):
    user = _create_user(test_db)

    response = client.post("/api/v1/auth/forgot-password", json={"email": user.email})

    assert response.status_code == 200
    assert response.json()["message"] == "אם קיים משתמש עם האימייל הזה, נשלחו הוראות לאיפוס סיסמה"
    records = test_db.scalars(
        select(PasswordResetToken).filter(PasswordResetToken.user_id == user.id)
    ).all()
    assert len(records) == 1
    assert len(records[0].token_hash) == 64
    assert records[0].used_at is None


def test_forgot_password_does_not_reveal_missing_user(client, test_db):
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing.reset@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "אם קיים משתמש עם האימייל הזה, נשלחו הוראות לאיפוס סיסמה"
    assert test_db.scalar(select(func.count()).select_from(PasswordResetToken)) == 0


def test_reset_password_uses_token_once_and_invalidates_existing_access_token(client, test_db):
    user = _create_user(test_db)
    login = client.post("/api/v1/auth/login", json={"email": user.email, "password": "password123"})
    old_access_token = login.json()["access_token"]
    raw_token = "raw-reset-token"
    token_record = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=utcnow() + timedelta(minutes=30),
    )
    test_db.add(token_record)
    test_db.commit()

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "Password123!"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "הסיסמה אופסה בהצלחה"
    test_db.refresh(token_record)
    test_db.refresh(user)
    assert token_record.used_at is not None
    assert AuthService.verify_password("Password123!", user.password_hash)

    protected_response = client.get(
        "/api/v1/clients",
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    assert protected_response.status_code == 401

    reuse_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "Password123!"},
    )
    assert reuse_response.status_code == 400
