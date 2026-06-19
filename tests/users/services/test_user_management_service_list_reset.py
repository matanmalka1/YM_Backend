import pytest

from app.core.exceptions import NotFoundError
from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus
from app.users.repositories.user_audit_log_repository import UserAuditLogRepository
from app.users.repositories.user_repository import UserRepository
from app.users.services.user_auth_service import AuthService
from app.users.services.user_management_service import UserManagementService


def _managed_user(test_db, *, email: str, is_active: bool = True) -> User:
    user = User(
        full_name="Managed Account",
        email=email,
        password_hash=AuthService.hash_password("password123"),
        role=UserRole.SECRETARY,
        is_active=is_active,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_list_users_and_reset_password(test_db, test_user):
    service = UserManagementService(test_db)
    user_repo = UserRepository(test_db)
    target = _managed_user(test_db, email="reset.target@example.com")
    inactive = _managed_user(test_db, email="reset.other@example.com", is_active=False)

    items, total = service.list_users(actor_role=UserRole.ADVISOR, page=1, page_size=10)
    assert total >= 3
    assert target.id in {u.id for u in items}
    assert inactive.id in {u.id for u in items}

    active_items, active_total = service.list_users(
        actor_role=UserRole.ADVISOR,
        page=1,
        page_size=10,
        is_active=True,
    )
    assert active_total == 2
    assert all(item.is_active is True for item in active_items)

    inactive_items, inactive_total = service.list_users(
        actor_role=UserRole.ADVISOR,
        page=1,
        page_size=10,
        is_active=False,
    )
    assert inactive_total == 1
    assert {item.id for item in inactive_items} == {inactive.id}

    before_token_version = user_repo.get_by_id(target.id).token_version
    updated = service.reset_password(
        actor_user_id=test_user.id,
        actor_role=UserRole.ADVISOR,
        target_user_id=target.id,
        new_password="Newpassword123!",
    )
    assert updated.id == target.id
    assert updated.token_version == before_token_version + 1
    assert AuthService.verify_password("Newpassword123!", updated.password_hash) is True

    audit_repo = UserAuditLogRepository(test_db)
    password_reset_logs = audit_repo.list(
        page=1,
        page_size=10,
        action=AuditAction.PASSWORD_RESET,
        target_user_id=target.id,
    )
    assert len(password_reset_logs) == 1
    assert password_reset_logs[0].status == AuditStatus.SUCCESS

    with pytest.raises(NotFoundError):
        service.reset_password(
            actor_user_id=test_user.id,
            actor_role=UserRole.ADVISOR,
            target_user_id=999999,
            new_password="Newpassword123!",
        )


def test_list_users_filters_by_search(test_db):
    service = UserManagementService(test_db)
    name_match = _managed_user(test_db, email="name-match@example.com")
    name_match.full_name = "Dana Search"
    email_match = _managed_user(test_db, email="mail.match@example.com")
    email_match.full_name = "Different Name"
    test_db.commit()

    items_by_name, total_by_name = service.list_users(
        actor_role=UserRole.ADVISOR,
        page=1,
        page_size=10,
        search="Dana",
    )
    items_by_email, total_by_email = service.list_users(
        actor_role=UserRole.ADVISOR,
        page=1,
        page_size=10,
        search="mail.match",
    )

    assert total_by_name == 1
    assert [item.id for item in items_by_name] == [name_match.id]
    assert total_by_email == 1
    assert [item.id for item in items_by_email] == [email_match.id]
