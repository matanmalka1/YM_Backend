from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random
from typing import Any

from sqlalchemy import func, select

from app.audit.audit_constants import ENTITY_BUSINESS, ENTITY_CLIENT
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.businesses.models.business import Business
from app.users.models.user import User, UserRole
from app.users.models.user_audit_log import AuditAction, AuditStatus, UserAuditLog

from ..data.constants import DEFAULT_PASSWORD_HASH
from ..data.demo_catalog import mobile_phone
from ..data.random_utils import full_name
from ..data.realistic_seed_text import STAFF_DIRECTORY


def get_existing_users(db) -> list[User]:
    return list(db.execute(select(User).order_by(User.id)).scalars())


def create_users(db, rng: Random, cfg) -> list[User]:
    users: list[User] = []
    existing_users = int(db.execute(select(func.count()).select_from(User)).scalar_one())
    for i in range(cfg.users):
        serial = existing_users + i + 1
        staff_profile = STAFF_DIRECTORY[i % len(STAFF_DIRECTORY)]
        role = UserRole[staff_profile["role"]]
        user = User(
            full_name=staff_profile["name"] if serial <= len(STAFF_DIRECTORY) else full_name(rng),
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
                actor_display_name=user.full_name,
                target_user_id=user.id,
                target_display_name=user.full_name,
                email=user.email,
                status=AuditStatus.SUCCESS,
                reason=None,
                metadata_json={"source": "seed"},
                created_at=datetime.now(UTC) - timedelta(days=rng.randint(0, 30)),
            )
        )
        if rng.random() < 0.3:
            db.add(
                UserAuditLog(
                    action=AuditAction.LOGIN_FAILURE,
                    actor_user_id=None,
                    target_user_id=user.id,
                    target_display_name=user.full_name,
                    email=user.email,
                    status=AuditStatus.FAILURE,
                    reason="invalid_password",
                    metadata_json={"source": "seed"},
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
    # Route through EntityAuditWriter so seeded rows match production: namespaced
    # actions, metadata_json, and §5a/§16 validation. Backdate performed_at after.
    writer = EntityAuditWriter(db)
    actor = users[0]
    clients_by_legal_entity_id = {client.legal_entity_id: client for client in clients}
    for client in clients:
        entry = writer.record_create(
            ENTITY_CLIENT,
            client.id,
            actor.id,
            actor_display_name=actor.full_name,
            metadata_json={"client_record_id": client.id},
        )
        entry.performed_at = datetime.now(UTC) - timedelta(days=rng.randint(30, 365))
    for business in businesses:
        business_actor = rng.choice(users)
        client = clients_by_legal_entity_id[business.legal_entity_id]
        record = writer.record_create if rng.random() < 0.5 else writer.record_update
        entry = record(
            ENTITY_BUSINESS,
            business.id,
            business_actor.id,
            actor_display_name=business_actor.full_name,
            metadata_json={"client_record_id": client.id, "business_id": business.id},
        )
        entry.performed_at = datetime.now(UTC) - timedelta(days=rng.randint(1, 180))
    db.flush()
