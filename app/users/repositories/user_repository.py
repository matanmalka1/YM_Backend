from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.common.repositories.base_repository import BaseRepository
from app.users.models.user import User, UserRole
from app.utils.time_utils import utcnow


@dataclass(frozen=True)
class AuthSubject:
    id: int
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    token_version: int


class UserRepository(BaseRepository[User]):
    """Data access layer for User entities."""

    model = User

    def __init__(self, db: Session):
        super().__init__(db)

    def get_auth_subject_by_id(self, user_id: int) -> AuthSubject | None:
        """Fetch only the columns needed for per-request JWT validation.

        Returns an immutable DTO — no ORM identity, no lazy loads.
        """
        row = self.db.execute(
            select(
                User.id,
                User.full_name,
                User.email,
                User.role,
                User.is_active,
                User.token_version,
            ).where(User.id == user_id)
        ).first()
        if row is None:
            return None
        return AuthSubject(
            id=row.id,
            full_name=row.full_name,
            email=row.email,
            role=row.role,
            is_active=row.is_active,
            token_version=row.token_version,
        )

    def get_by_email(self, email: str) -> User | None:
        """Retrieve user by email."""
        return self.db.scalars(select(User).where(User.email == email)).first()

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[User]:
        """List users with pagination."""
        stmt = self._apply_list_filters(
            select(User),
            is_active=is_active,
            search=search,
        ).order_by(User.id.asc())
        stmt = self.apply_pagination(stmt, page, page_size)
        return list(self.db.scalars(stmt).all())

    def count(
        self,
        is_active: bool | None = None,
        search: str | None = None,
        *,
        include_deleted: bool = False,
    ) -> int:
        """Count users."""
        stmt = self._apply_list_filters(
            select(func.count(User.id)),
            is_active=is_active,
            search=search,
        )
        return self.db.scalar(stmt)

    def _apply_list_filters(
        self,
        stmt,
        *,
        is_active: bool | None = None,
        search: str | None = None,
    ):
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
        return stmt

    def list_by_ids(self, user_ids: list[int]) -> list[User]:
        """Batch fetch users by a list of IDs (single query)."""
        if not user_ids:
            return []
        return self.db.scalars(select(User).where(User.id.in_(user_ids))).all()

    def create(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        role: UserRole,
        phone: str | None = None,
    ) -> User:
        """Create new user."""
        user = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=role,
            phone=phone,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def update_last_login(self, user_id: int) -> None:
        """Update last login timestamp."""
        self.db.execute(update(User).where(User.id == user_id).values(last_login_at=utcnow()))
        self.db.flush()

    def update(self, user_id: int, **fields) -> User | None:
        """Update user fields."""
        user = self.get_by_id(user_id)
        return self._update_entity(user, **fields)

    def activate(self, user_id: int) -> User | None:
        """Activate user."""
        return self.update(user_id, is_active=True)

    def bump_token_version(self, user_id: int) -> User | None:
        """Invalidate all active tokens for a user without changing any other field."""
        user = self.get_by_id(user_id)
        if not user:
            return None

        user.token_version += 1
        self.db.flush()
        return user

    def deactivate_and_bump_token(self, user_id: int) -> User | None:
        """Deactivate user and invalidate active tokens."""
        user = self.get_by_id(user_id)
        if not user:
            return None

        user.is_active = False
        user.token_version += 1
        self.db.flush()
        return user

    def set_password_and_bump_token(self, user_id: int, password_hash: str) -> User | None:
        """Update password hash and invalidate active tokens."""
        user = self.get_by_id(user_id)
        if not user:
            return None

        user.password_hash = password_hash
        user.token_version += 1
        self.db.flush()
        return user
