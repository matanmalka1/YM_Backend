import pytest

from app.core.exceptions import AppError, ForbiddenError
from app.users.models.user import UserRole
from app.users.user_management_policies import (
    ensure_advisor,
    validate_password,
)


def test_ensure_advisor_rejects_non_advisor_roles():
    ensure_advisor(UserRole.ADVISOR)

    with pytest.raises(ForbiddenError) as exc_info:
        ensure_advisor(UserRole.SECRETARY)
    assert exc_info.value.code == "USER.FORBIDDEN"


def test_validate_password_enforces_minimum_length():
    validate_password("Password123!")

    with pytest.raises(AppError) as exc_info:
        validate_password("short")
    assert exc_info.value.code == "USER.INVALID_PASSWORD"


@pytest.mark.parametrize(
    "password", ["", "        ", "password123!", "PASSWORD123!", "Password123"]
)
def test_validate_password_enforces_complexity(password):
    with pytest.raises(AppError) as exc_info:
        validate_password(password)
    assert exc_info.value.code == "USER.INVALID_PASSWORD"
