from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random
from typing import Any

from sqlalchemy import func, select

from app.audit.audit_constants import (
    ACTION_CREATED,
    ACTION_UPDATED,
    ENTITY_BUSINESS,
    ENTITY_CLIENT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.businesses.models.business import Business
from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus, UserAuditLog

from ..data.constants import DEFAULT_PASSWORD_HASH
from ..data.demo_catalog import mobile_phone
from ..data.realistic_seed_text import STAFF_DIRECTORY
from ..data.random_utils import full_name


def get_existing_users(db) -> list[User]:
    return list(db.execute(select(User).order_by(User.id)).scalars())


def create_users(db, rng: Random, cfg) -> list[User]:
    users: list[User] = []
    existing_users = int(
        db.execute(select(func.count()).select_from(User)).scalar_one()
    )
    for i in range(cfg.users):
        serial = existing_users + i + 1
        staff_profile = STAFF_DIRECTORY[i % len(STAFF_DIRECTORY)]
        role = UserRole[staff_profile["role"]]
        user = User(
            full_name=staff_profile["name"]
            if serial <= len(STAFF_DIRECTORY)
            else full_name(rng),
            email=f"matan{1390 + serial}@gmail.com",
            phone=mobile_phone(rng),
            password_hash=DEFAULT_PASSWORD_HASH,
            role=role,
            is_active=True if i == 0 else rng.random() > 0.1,
            token_version=0,
            created_at=datetime.now(UTC) - timedelta(days=rng.randint(10, 300)),
            last_login_at=datetime.now(UTC) - timedelta(days=rng.randint(0, 30)),
        )
        db.add(user)
        users.append(user)
    db.flush()
    return users


def create_user_audit_logs(db, rng: Random, users: list[User]) -> None:
    for user in users:
        db.add(
            UserAuditLog(
                action=AuditAction.LOGIN_SUCCESS,
                actor_user_id=user.id,
                target_user_id=user.id,
                email=user.email,
                status=AuditStatus.SUCCESS,
                reason=None,
                metadata_json='{"source":"seed"}',
                created_at=datetime.now(UTC) - timedelta(days=rng.randint(0, 30)),
            )
        )
        if rng.random() < 0.3:
            db.add(
                UserAuditLog(
                    action=AuditAction.LOGIN_FAILURE,
                    actor_user_id=None,
                    target_user_id=user.id,
                    email=user.email,
                    status=AuditStatus.FAILURE,
                    reason="invalid_password",
                    metadata_json='{"source":"seed"}',
                    created_at=datetime.now(UTC) - timedelta(days=rng.randint(0, 30)),
                )
            )
    db.flush()


def create_entity_audit_logs(
    db,
    rng: Random,
    users: list[User],
    businesses: list[Business],
    clients: list[Any],
) -> None:
    actor = users[0]
    for client in clients:
        db.add(
            EntityAuditLog(
                entity_type=ENTITY_CLIENT,
                entity_id=client.id,
                performed_by=actor.id,
                action=ACTION_CREATED,
                performed_at=datetime.now(UTC) - timedelta(days=rng.randint(30, 365)),
            )
        )
    for business in businesses:
        db.add(
            EntityAuditLog(
                entity_type=ENTITY_BUSINESS,
                entity_id=business.id,
                performed_by=rng.choice(users).id,
                action=rng.choice([ACTION_CREATED, ACTION_UPDATED]),
                performed_at=datetime.now(UTC) - timedelta(days=rng.randint(1, 180)),
            )
        )
    db.flush()
