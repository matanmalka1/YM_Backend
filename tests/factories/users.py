from __future__ import annotations

from itertools import count

from sqlalchemy.orm import Session

from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService


def create_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str = "password123",
    role: UserRole = UserRole.ADVISOR,
    is_active: bool = True,
    commit: bool = False,
) -> User:
    user = User(
        full_name=full_name,
        email=email,
        password_hash=AuthService.hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    return user


class UserFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        full_name: str = "Test User",
        email: str | None = None,
        password: str = "password123",
        role: UserRole = UserRole.ADVISOR,
        is_active: bool = True,
        commit: bool = False,
    ) -> User:
        sequence = next(self._sequence)
        return create_user(
            self.db,
            full_name=full_name,
            email=email or f"test-user-{sequence}@example.com",
            password=password,
            role=role,
            is_active=is_active,
            commit=commit,
        )
