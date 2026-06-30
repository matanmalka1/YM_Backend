from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus
from app.users.repositories.user_audit_log_repository import UserAuditLogRepository
from app.users.repositories.user_repository import UserRepository
from app.users.services.user_auth_service import AuthService
from app.users.services.user_token_service import decode_access_token
from tests.factories import create_user


def _user(test_db, *, email: str, is_active: bool = True) -> User:
    user = create_user(
        test_db,
        full_name="Auth Service User",
        email=email,
        password="password123",
        role=UserRole.ADVISOR,
        is_active=is_active,
        commit=True,
    )
    return user


def test_authenticate_handles_user_not_found_and_inactive_user(test_db):
    service = AuthService(test_db)
    inactive_user = _user(test_db, email="inactive.auth@example.com", is_active=False)

    assert service.authenticate("missing.auth@example.com", "password123") is None
    assert service.authenticate(inactive_user.email, "password123") is None

    audit_repo = UserAuditLogRepository(test_db)
    entries = audit_repo.list(page=1, page_size=10)
    reasons = {(entry.action, entry.reason) for entry in entries}
    assert (AuditAction.LOGIN_FAILURE, "user_not_found") in reasons
    assert (AuditAction.LOGIN_FAILURE, "inactive_user") in reasons


def test_authenticate_success_and_logout_bump_token_and_write_audit(test_db):
    service = AuthService(test_db)
    repo = UserRepository(test_db)
    user = _user(test_db, email="active.auth@example.com", is_active=True)

    before = repo.get_by_id(user.id)
    assert before.last_login_at is None
    assert before.token_version == 0

    authenticated = service.authenticate(user.email, "password123")
    assert authenticated is not None

    after_login = repo.get_by_id(user.id)
    assert after_login.last_login_at is not None
    assert after_login.token_version == 0

    service.logout_user(user_id=after_login.id, email=after_login.email)
    after_logout = repo.get_by_id(user.id)
    assert after_logout.token_version == 1

    audit_repo = UserAuditLogRepository(test_db)
    entries = audit_repo.list(page=1, page_size=20, target_user_id=user.id)
    action_status_pairs = {(entry.action, entry.status) for entry in entries}
    assert (AuditAction.LOGIN_SUCCESS, AuditStatus.SUCCESS) in action_status_pairs
    assert (AuditAction.LOGOUT, AuditStatus.SUCCESS) in action_status_pairs


def test_decode_token_rejects_missing_fields_expired_and_invalid_tokens(test_user):
    # Missing "email" from required fields.
    now = datetime.now(UTC)
    missing_required_token = jwt.encode(
        {
            "sub": str(test_user.id),
            "role": test_user.role.value,
            "tv": test_user.token_version,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert decode_access_token(missing_required_token) is None

    expired_token = jwt.encode(
        {
            "sub": str(test_user.id),
            "email": test_user.email,
            "role": test_user.role.value,
            "tv": test_user.token_version,
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert decode_access_token(expired_token) is None

    assert decode_access_token("not-a-jwt") is None
