from dataclasses import dataclass

import bcrypt
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError
from app.core.logging_config import get_logger
from app.users.models.user import User
from app.users.models.user_audit_log import AuditAction, AuditStatus
from app.users.repositories.user_repository import UserRepository
from app.users.services.audit_log_service import AuditLogService
from app.users.services.token_service import (
    decode_refresh_token,
    generate_access_token,
    generate_refresh_token,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class AuthBundle:
    access_token: str
    refresh_token: str
    user: User


class InvalidRefreshTokenError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "טוקן הרענון אינו תקין או שפג תוקפו",
            ErrorCode.AUTH_INVALID_REFRESH_TOKEN,
            status_code=401,
        )


class AuthService:
    """Authentication and authorization business logic."""

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.audit_log_service = AuditLogService(db)

    @staticmethod
    def hash_password(password: str) -> str:
        if len(password.encode()) > 72:
            raise ValueError("Password must not exceed 72 bytes")
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        if len(password.encode()) > 72:
            return False
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate user by email and password."""
        normalized_email = email.strip().lower()
        user = self.user_repo.get_by_email(normalized_email)

        if not user:
            logger.warning(f"Failed login attempt for email: {normalized_email}")
            self.audit_log_service.log(
                action=AuditAction.LOGIN_FAILURE,
                status=AuditStatus.FAILURE,
                email=normalized_email,
                reason="user_not_found",
            )
            return None

        if not user.is_active:
            logger.warning(f"Inactive user login attempt for email: {normalized_email}")
            self.audit_log_service.log(
                action=AuditAction.LOGIN_FAILURE,
                status=AuditStatus.FAILURE,
                target_user_id=user.id,
                email=normalized_email,
                reason="inactive_user",
            )
            return None

        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Invalid password for email: {normalized_email}")
            self.audit_log_service.log(
                action=AuditAction.LOGIN_FAILURE,
                status=AuditStatus.FAILURE,
                target_user_id=user.id,
                email=normalized_email,
                reason="invalid_password",
            )
            return None

        self.user_repo.update_last_login(user.id)
        self.audit_log_service.log(
            action=AuditAction.LOGIN_SUCCESS,
            status=AuditStatus.SUCCESS,
            actor_user_id=user.id,
            target_user_id=user.id,
            email=user.email,
        )
        logger.info(f"Successful login for user: {normalized_email}")
        return user

    def login(self, email: str, password: str) -> AuthBundle | None:
        user = self.authenticate(email, password)
        if user is None:
            return None
        return self.issue_auth_bundle(user)

    def logout_user(self, *, user_id: int, email: str) -> None:
        """
        Invalidate all active tokens for the user by bumping token_version.

        This ensures that any token — whether sent via cookie or Authorization header —
        is rejected on the next request, even before the JWT expiry time.
        """
        self.user_repo.bump_token_version(user_id)
        self.audit_log_service.log(
            action=AuditAction.LOGOUT,
            status=AuditStatus.SUCCESS,
            actor_user_id=user_id,
            target_user_id=user_id,
            email=email,
        )
        logger.info(f"User logged out and token invalidated: {email}")

    @staticmethod
    def issue_auth_bundle(user: User) -> AuthBundle:
        return AuthBundle(
            access_token=generate_access_token(user),
            refresh_token=generate_refresh_token(user),
            user=user,
        )

    def refresh_access_token(self, refresh_token: str | None) -> str:
        if not refresh_token:
            raise InvalidRefreshTokenError()

        payload = decode_refresh_token(refresh_token)
        if not payload:
            raise InvalidRefreshTokenError()

        try:
            user_id = int(payload["sub"])
            token_version = int(payload["tv"])
        except (ValueError, KeyError) as exc:
            raise InvalidRefreshTokenError() from exc

        user = self.user_repo.get_by_id(user_id)
        if not user or not user.is_active or user.token_version != token_version:
            raise InvalidRefreshTokenError()

        return generate_access_token(user)

    def logout_by_refresh_token(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return

        payload = decode_refresh_token(refresh_token)
        if not payload:
            return

        try:
            user_id = int(payload["sub"])
        except ValueError, KeyError:
            return

        user = self.user_repo.get_by_id(user_id)
        if not user:
            return
        self.logout_user(user_id=user.id, email=user.email)
