from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.audit.audit_constants import (
    ACTION_ANNEX_LINE_UPDATED,
    ACTION_STATUS_CHANGED,
    ACTION_UPDATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_CLIENT,
    entity_action,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.common.enums import EntityType
from app.core.exceptions import AppError

_NAME = "פלוני אלמוני"


def test_writer_stores_dict_as_json_object(test_db, test_user):
    EntityAuditWriter(test_db).record_update(
        ENTITY_CLIENT,
        10,
        test_user.id,
        old_value={"full_name": "ישן"},
        new_value={"full_name": "חדש"},
        actor_display_name=_NAME,
        metadata_json={"client_record_id": 10},
    )

    entry = test_db.scalars(select(EntityAuditLog)).one()
    assert entry.action == entity_action(ENTITY_CLIENT, ACTION_UPDATED)
    # Stored as a JSON object (dict), not a json.dumps string.
    assert entry.old_value == {"full_name": "ישן"}
    assert entry.new_value == {"full_name": "חדש"}
    assert entry.actor_type == "user"


def test_writer_wraps_plain_string(test_db, test_user):
    writer = EntityAuditWriter(test_db)
    assert writer._serialize_value("old") == {"value": "old"}
    assert writer._serialize_value("new") == {"value": "new"}


def test_writer_records_actor_display_name_snapshot(test_db, test_user):
    EntityAuditWriter(test_db).record_create(
        ENTITY_CLIENT,
        10,
        test_user.id,
        new_value={"full_name": "חדש"},
        actor_display_name=_NAME,
        metadata_json={"client_record_id": 10},
    )

    entry = test_db.scalars(select(EntityAuditLog)).one()
    assert entry.actor_type == "user"
    assert entry.actor_display_name == _NAME


def test_writer_serializes_enum_inside_dict_as_value(test_db, test_user):
    EntityAuditWriter(test_db).record_update(
        ENTITY_CLIENT,
        10,
        test_user.id,
        new_value={
            "entity_type": EntityType.COMPANY_LTD,
            "phone": [EntityType.OSEK_MURSHE],
        },
        actor_display_name=_NAME,
        metadata_json={"client_record_id": 10},
    )

    entry = test_db.scalars(select(EntityAuditLog)).one()
    assert entry.new_value == {
        "entity_type": EntityType.COMPANY_LTD.value,
        "phone": [EntityType.OSEK_MURSHE.value],
    }


def test_writer_serializes_date_and_decimal_inside_dict(test_db, test_user):
    EntityAuditWriter(test_db).append(
        entity_type=ENTITY_ANNUAL_REPORT,
        entity_id=10,
        actor_id=test_user.id,
        action=ACTION_ANNEX_LINE_UPDATED,
        new_value={"data": {"opened_at": date(2026, 5, 8), "amount": Decimal("12.30")}},
        actor_display_name=_NAME,
        metadata_json={
            "client_record_id": 10,
            "tax_year": 2026,
            "line_id": 20,
            "schedule_id": 30,
            "line_number": 1,
        },
    )

    entry = test_db.scalars(select(EntityAuditLog)).one()
    assert entry.new_value == {"data": {"opened_at": "2026-05-08", "amount": "12.30"}}


def test_writer_rejects_user_actor_without_actor_id(test_db):
    # The no-op for actor_id=None is gone (§2/§17): a user write with no
    # performed_by fails the §5a actor matrix and rolls back.
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).record_create(
            ENTITY_CLIENT,
            10,
            None,
            new_value={"x": 1},
            actor_display_name=_NAME,
            metadata_json={"client_record_id": 10},
        )


def test_record_status_change_stores_status_payload(test_db, test_user):
    EntityAuditWriter(test_db).record_status_change(
        ENTITY_ANNUAL_REPORT,
        10,
        test_user.id,
        "draft",
        "active",
        actor_display_name=_NAME,
        metadata_json={"client_record_id": 10, "tax_year": 2026},
    )

    entry = test_db.scalars(select(EntityAuditLog)).one()
    assert entry.action == entity_action(ENTITY_ANNUAL_REPORT, ACTION_STATUS_CHANGED)
    assert entry.old_value == {"status": "draft"}
    assert entry.new_value == {"status": "active"}
