from app.core.error_codes import ErrorCode
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus
from app.users.repositories.user_repository import UserRepository
from app.users.services.audit_log_service import AuditLogService
from app.users.services.auth_service import AuthService
from app.users.services.user_management_policies import (
    ensure_advisor,
    validate_password,
)

IMMUTABLE_UPDATE_FIELDS = {
    "id",
    "token_version",
    "created_at",
    "last_login_at",
    "is_active",
}

_USER_EMAIL_EXISTS = "כבר קיים משתמש עם המייל {email}"
_USER_IMMUTABLE_FIELDS = "לא ניתן לעדכן שדות שאינם ניתנים לשינוי: {disallowed}"
_USER_NO_FIELDS_PROVIDED = "חובה לספק לפחות שדה אחד הניתן לשינוי"
_USER_CANNOT_DEACTIVATE_SELF = "אינך יכול להשבית את החשבון שלך"


def get_user_or_raise(repo: UserRepository, user_id: int) -> User:
    user = repo.get_by_id(user_id)
    if not user:
        raise NotFoundError(f"משתמש {user_id} לא נמצא", ErrorCode.USER_NOT_FOUND)
    return user


class UserManagementService:
    """User lifecycle management and authorization enforcement."""

    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)
        self.audit_log_service = AuditLogService(db)

    def create_user(
        self,
        actor_user_id: int,
        actor_role: UserRole,
        full_name: str,
        email: str,
        role: UserRole,
        password: str,
        phone: str | None = None,
    ) -> User:
        ensure_advisor(actor_role)
        validate_password(password)

        if self.user_repo.get_by_email(email):
            raise ConflictError(_USER_EMAIL_EXISTS.format(email=email), ErrorCode.USER_CONFLICT)

        user = self.user_repo.create(
            full_name=full_name,
            email=email,
            password_hash=AuthService.hash_password(password),
            role=role,
            phone=phone,
        )
        self.audit_log_service.log(
            action=AuditAction.USER_CREATED,
            status=AuditStatus.SUCCESS,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
        )
        return user

    def list_users(
        self,
        actor_role: UserRole,
        page: int,
        page_size: int,
        is_active: bool | None = None,
        search: str | None = None,
    ):
        ensure_advisor(actor_role)
        items = self.user_repo.list(
            page=page,
            page_size=page_size,
            is_active=is_active,
            search=search,
        )
        total = self.user_repo.count(is_active=is_active, search=search)
        return items, total

    def get_user(self, actor_role: UserRole, user_id: int) -> User:
        ensure_advisor(actor_role)
        return get_user_or_raise(self.user_repo, user_id)

    def update_user(
        self,
        actor_user_id: int,
        actor_role: UserRole,
        user_id: int,
        **fields,
    ) -> User:
        ensure_advisor(actor_role)
        if "email" in fields:
            existing = self.user_repo.get_by_email(fields["email"])
            if existing and existing.id != user_id:
                raise ConflictError(
                    _USER_EMAIL_EXISTS.format(email=fields["email"]), ErrorCode.USER_CONFLICT
                )

        immutable_attempt = IMMUTABLE_UPDATE_FIELDS.intersection(fields.keys())
        if immutable_attempt:
            disallowed = ", ".join(sorted(immutable_attempt))
            raise AppError(
                _USER_IMMUTABLE_FIELDS.format(disallowed=disallowed),
                ErrorCode.USER_INVALID_UPDATE,
            )

        if not fields:
            raise AppError(_USER_NO_FIELDS_PROVIDED, ErrorCode.USER_NO_FIELDS_PROVIDED)

        get_user_or_raise(self.user_repo, user_id)
        user = self.user_repo.update(user_id, **fields)

        self.audit_log_service.log(
            action=AuditAction.USER_UPDATED,
            status=AuditStatus.SUCCESS,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"updated_fields": sorted(fields.keys())},
        )
        return user

    def activate_user(self, actor_user_id: int, actor_role: UserRole, user_id: int) -> User:
        ensure_advisor(actor_role)
        get_user_or_raise(self.user_repo, user_id)
        user = self.user_repo.activate(user_id)
        self.audit_log_service.log(
            action=AuditAction.USER_ACTIVATED,
            status=AuditStatus.SUCCESS,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
        )
        return user

    def deactivate_user(
        self,
        actor_user_id: int,
        actor_role: UserRole,
        target_user_id: int,
    ) -> User:
        ensure_advisor(actor_role)
        if actor_user_id == target_user_id:
            raise ForbiddenError(_USER_CANNOT_DEACTIVATE_SELF, ErrorCode.USER_FORBIDDEN)

        get_user_or_raise(self.user_repo, target_user_id)
        user = self.user_repo.deactivate_and_bump_token(target_user_id)

        self.audit_log_service.log(
            action=AuditAction.USER_DEACTIVATED,
            status=AuditStatus.SUCCESS,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
        )
        return user

    def reset_password(
        self,
        actor_user_id: int,
        actor_role: UserRole,
        target_user_id: int,
        new_password: str,
    ) -> User:
        ensure_advisor(actor_role)
        validate_password(new_password)

        get_user_or_raise(self.user_repo, target_user_id)
        password_hash = AuthService.hash_password(new_password)
        user = self.user_repo.set_password_and_bump_token(target_user_id, password_hash)

        self.audit_log_service.log(
            action=AuditAction.PASSWORD_RESET,
            status=AuditStatus.SUCCESS,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
        )
        return user
