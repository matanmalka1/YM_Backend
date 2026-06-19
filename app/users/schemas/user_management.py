from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.api_types import ApiDateTime, NonBlankStr, PaginatedResponse
from app.core.schemas.validation import NonEmptyUpdateMixin
from app.users.models.user import UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus
from app.users.user_management_policies import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
)


class UserCreateRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    role: UserRole
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserUpdateRequest(NonEmptyUpdateMixin):
    full_name: NonBlankStr | None = None
    phone: str | None = None
    role: UserRole | None = None
    email: EmailStr | None = None

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> UserUpdateRequest:
        # phone is nullable (explicit null clears it); role/email/full_name map
        # to non-nullable columns, so explicit null is invalid.
        for field in ("role", "email", "full_name"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"השדה {field} לא יכול להיות null")
        return self


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserManagementResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str | None = None
    role: UserRole
    is_active: bool
    created_at: ApiDateTime
    last_login_at: ApiDateTime | None = None

    model_config = {"from_attributes": True}


class UserManagementListResponse(PaginatedResponse[UserManagementResponse]):
    pass


class UserAuditLogResponse(BaseModel):
    id: int
    action: AuditAction
    actor_user_id: int | None = None
    target_user_id: int | None = None
    email: str | None = None
    status: AuditStatus
    reason: str | None = None
    metadata: dict | None = None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class UserAuditLogListResponse(PaginatedResponse[UserAuditLogResponse]):
    pass
