import re

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ForbiddenError
from app.users.models.user import UserRole

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
_PASSWORD_RE = re.compile(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*[^a-zA-Z0-9]).{8,}$")


def ensure_advisor(actor_role: UserRole) -> None:
    if actor_role != UserRole.ADVISOR:
        raise ForbiddenError("רק יועצים יכולים לנהל משתמשים", ErrorCode.USER_FORBIDDEN)


def validate_password(password: str) -> None:
    if not password or not password.strip():
        raise AppError("הסיסמה לא יכולה להיות ריקה", ErrorCode.USER_INVALID_PASSWORD)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AppError("הסיסמה חייבת להכיל לפחות 8 תווים", ErrorCode.USER_INVALID_PASSWORD)
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AppError("הסיסמה ארוכה מדי", ErrorCode.USER_INVALID_PASSWORD)
    if not _PASSWORD_RE.match(password):
        raise AppError(
            "הסיסמה חייבת להכיל לפחות אות גדולה, אות קטנה ותו מיוחד אחד",
            ErrorCode.USER_INVALID_PASSWORD,
        )


__all__ = ["MAX_PASSWORD_LENGTH", "MIN_PASSWORD_LENGTH", "ensure_advisor", "validate_password"]
