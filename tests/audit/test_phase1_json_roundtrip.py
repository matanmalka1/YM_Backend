"""Phase 1 — JSON-object round-trip + actor-snapshot contract.

EntityAuditLog stores old_value/new_value/metadata_json as JSON objects (dict),
not json.dumps strings; UserAuditLog stores metadata_json as a JSON object too.
Both carry immutable actor-name snapshots. Response schemas expose objects.
"""

from sqlalchemy import select

from app.audit.audit_constants import ENTITY_CLIENT
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.schemas.audit_entity_audit_log import EntityAuditLogResponse
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.users.models.user_audit_log import AuditAction, AuditStatus, UserAuditLog
from app.users.schemas.user_management import UserAuditLogResponse
from app.users.services.user_audit_log_service import AuditLogService


def _user(user_factory, *, email: str, name: str = "מבקר"):
    return user_factory(full_name=name, email=email)


def test_entity_audit_metadata_json_round_trips_as_object(test_db, test_user):
    EntityAuditWriter(test_db).append(
        entity_type=ENTITY_CLIENT,
        entity_id=7,
        actor_id=test_user.id,
        action="client.updated",
        old_value={"full_name": "ישן"},
        new_value={"full_name": "חדש"},
        metadata_json={"client_record_id": "7"},
        actor_display_name=test_user.full_name,
    )

    entry = test_db.scalars(select(EntityAuditLog)).one()
    # Stored and read back as dicts — no json.dumps / json.loads.
    assert entry.old_value == {"full_name": "ישן"}
    assert entry.new_value == {"full_name": "חדש"}
    assert entry.metadata_json == {"client_record_id": "7"}
    assert entry.actor_type == "user"
    assert entry.actor_display_name == test_user.full_name


def test_entity_audit_response_exposes_objects_not_strings(test_db, test_user):
    EntityAuditWriter(test_db).record_update(
        ENTITY_CLIENT,
        7,
        test_user.id,
        old_value={"phone": "1"},
        new_value={"phone": "2"},
        actor_display_name=test_user.full_name,
        metadata_json={"client_record_id": 7},
    )
    entry = test_db.scalars(select(EntityAuditLog)).one()

    resp = EntityAuditLogResponse.model_validate(entry)
    assert resp.old_value == {"phone": "1"}
    assert resp.new_value == {"phone": "2"}
    assert resp.actor_type == "user"
    assert resp.actor_display_name == test_user.full_name
    dumped = resp.model_dump()
    assert isinstance(dumped["old_value"], dict)
    assert isinstance(dumped["new_value"], dict)


def test_user_audit_metadata_round_trips_as_object_with_snapshots(test_db, user_factory):
    actor = _user(user_factory, email="p1.actor@example.com", name="יוסי המבצע")
    target = _user(user_factory, email="p1.target@example.com", name="דנה המטרה")
    service = AuditLogService(test_db)

    service.log(
        action=AuditAction.USER_UPDATED,
        status=AuditStatus.SUCCESS,
        actor_user_id=actor.id,
        actor_display_name=actor.full_name,
        target_user_id=target.id,
        target_display_name=target.full_name,
        email=target.email,
        metadata={"updated_fields": ["role", "phone"]},
    )

    row = test_db.scalars(select(UserAuditLog)).one()
    # metadata_json is a dict (JSONB), not a json.dumps string.
    assert row.metadata_json == {"updated_fields": ["role", "phone"]}
    assert row.actor_display_name == "יוסי המבצע"
    assert row.target_display_name == "דנה המטרה"

    items, total = service.list_logs(page=1, page_size=10)
    assert total == 1
    item = items[0]
    assert item["metadata"] == {"updated_fields": ["role", "phone"]}
    assert item["actor_display_name"] == "יוסי המבצע"
    assert item["target_display_name"] == "דנה המטרה"

    resp = UserAuditLogResponse(**item)
    assert resp.metadata == {"updated_fields": ["role", "phone"]}
    assert isinstance(resp.model_dump()["metadata"], dict)
    assert resp.actor_display_name == "יוסי המבצע"
    assert resp.target_display_name == "דנה המטרה"


def test_user_audit_metadata_none_stays_none(test_db, user_factory):
    actor = _user(user_factory, email="p1.none@example.com")
    AuditLogService(test_db).log(
        action=AuditAction.LOGIN_SUCCESS,
        status=AuditStatus.SUCCESS,
        actor_user_id=actor.id,
        actor_display_name=actor.full_name,
        email=actor.email,
    )
    row = test_db.scalars(select(UserAuditLog)).one()
    assert row.metadata_json is None
