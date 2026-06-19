from datetime import UTC, datetime, timedelta

from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus
from app.users.services.user_audit_log_service import AuditLogService
from app.users.services.user_auth_service import AuthService


def _user(test_db, *, email: str) -> User:
    user = User(
        full_name="Audit Service User",
        email=email,
        password_hash=AuthService.hash_password("password123"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_list_logs_returns_filtered_items_and_total(test_db):
    actor = _user(test_db, email="audit.actor@example.com")
    target = _user(test_db, email="audit.target@example.com")
    service = AuditLogService(test_db)

    service.log(
        action=AuditAction.LOGIN_SUCCESS,
        status=AuditStatus.SUCCESS,
        actor_user_id=actor.id,
        email=actor.email,
    )
    service.log(
        action=AuditAction.LOGIN_FAILURE,
        status=AuditStatus.FAILURE,
        actor_user_id=actor.id,
        target_user_id=target.id,
        email=actor.email,
        reason="bad-password",
    )

    filtered_items, filtered_total = service.list_logs(
        page=1,
        page_size=10,
        action=AuditAction.LOGIN_FAILURE,
        actor_user_id=actor.id,
        target_user_id=target.id,
        email=actor.email,
    )
    assert filtered_total == 1
    assert len(filtered_items) == 1
    assert filtered_items[0]["action"] == AuditAction.LOGIN_FAILURE

    created_after = datetime.now(UTC) - timedelta(minutes=1)
    created_before = datetime.now(UTC) + timedelta(minutes=1)
    all_items, all_total = service.list_logs(
        page=1,
        page_size=1,
        created_after=created_after,
        created_before=created_before,
    )
    assert all_total == 2
    assert len(all_items) == 1
