"""Phase 2 — registry-backed read flow, authorization, actor matrix, append-only,
fail-closed write validation, atomicity, and metadata enrichment.

Current-auth model only (ADVISOR + SECRETARY); no 403-by-role, owner/accountant,
or per-role redaction — those models do not exist.
"""

import pytest
from sqlalchemy import func, select

from app.audit.audit_constants import (
    ENTITY_CLIENT,
    ENTITY_SIGNATURE_REQUEST,
    entity_action,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.repositories.audit_entity_audit_log_repository import EntityAuditLogRepository
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.charges.models.charge import Charge, ChargeType
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import AppError
from app.users.repositories.user_audit_log_repository import UserAuditLogRepository

_NAME = "מבקר ביקורת"


def _write(test_db, test_user, entity_type, entity_id, *, metadata=None, action=None):
    if metadata is None:
        metadata = {"client_record_id": entity_id}
    EntityAuditWriter(test_db).append(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=test_user.id,
        action=action or entity_action(entity_type, "updated"),
        actor_display_name=_NAME,
        metadata_json=metadata,
    )
    test_db.commit()


@pytest.mark.parametrize("headers_fixture", ["advisor_headers", "secretary_headers"])
def test_both_roles_may_read_audit(
    request, client, test_db, test_user, create_client_with_business, headers_fixture
):
    headers = request.getfixturevalue(headers_fixture)
    client_record, _ = create_client_with_business(id_number=f"P2-ROLE-{headers_fixture[:3]}")
    _write(test_db, test_user, ENTITY_CLIENT, client_record.id)

    resp = client.get(f"/api/v1/audit/client/{client_record.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert resp.json()["entity_deleted"] is False


def test_404_only_when_no_live_entity_and_no_history(client, advisor_headers):
    resp = client.get("/api/v1/audit/client/987654", headers=advisor_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AUDIT.ENTITY_NOT_FOUND"


def test_soft_deleted_entity_history_is_readable_and_flagged(
    client, test_db, test_user, advisor_headers, create_client_with_business
):
    client_record, _ = create_client_with_business(id_number="P2-SOFT")
    _write(test_db, test_user, ENTITY_CLIENT, client_record.id)
    ClientRecordRepository(test_db).soft_delete(client_record.id, deleted_by=test_user.id)
    test_db.commit()

    resp = client.get(f"/api/v1/audit/client/{client_record.id}", headers=advisor_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert payload["entity_deleted"] is True


def test_hard_deleted_history_resolved_from_audit_metadata(
    client, test_db, test_user, advisor_headers
):
    # No live ClientRecord with this id; only audit rows carrying client_record_id.
    ghost_id = 765432
    _write(
        test_db,
        test_user,
        ENTITY_CLIENT,
        ghost_id,
        metadata={"client_record_id": ghost_id},
    )

    resp = client.get(f"/api/v1/audit/client/{ghost_id}", headers=advisor_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert payload["entity_deleted"] is True


def test_both_roles_receive_same_signature_forensic_fields(
    request, client, test_db, test_user, advisor_headers, secretary_headers
):
    # signature_request is the sensitive type; under the current model both roles
    # see the same forensic metadata. Resolved from history (no live row needed).
    sig_id = 444777
    forensic = {
        "client_record_id": sig_id,
        "signer_name": "חותם חיצוני",
        "ip_address": "203.0.113.5",
        "user_agent": "Mozilla/5.0",
    }
    _write(
        test_db,
        test_user,
        ENTITY_SIGNATURE_REQUEST,
        sig_id,
        metadata=forensic,
        action="signature_request.viewed",
    )

    for headers in (advisor_headers, secretary_headers):
        resp = client.get(f"/api/v1/audit/signature_request/{sig_id}", headers=headers)
        assert resp.status_code == 200
        meta = resp.json()["items"][0]["metadata_json"]
        assert meta["ip_address"] == "203.0.113.5"
        assert meta["user_agent"] == "Mozilla/5.0"


# --------------------------------------------------------------------------- #
# Actor validation matrix (§5a)
# --------------------------------------------------------------------------- #
def test_actor_matrix_valid_user(test_db, test_user):
    EntityAuditWriter(test_db).append(
        entity_type=ENTITY_CLIENT,
        entity_id=1,
        actor_id=test_user.id,
        action=entity_action(ENTITY_CLIENT, "updated"),
        actor_display_name=_NAME,
        metadata_json={"client_record_id": 1},
    )  # no raise


def test_actor_matrix_valid_system(test_db):
    EntityAuditWriter(test_db).record_action(
        ENTITY_CLIENT,
        1,
        None,
        entity_action(ENTITY_CLIENT, "updated"),
        actor_type="system",
        actor_display_name="מערכת",
        metadata_json={"client_record_id": 1},
    )  # no raise


def test_actor_matrix_valid_external_signer(test_db):
    EntityAuditWriter(test_db).record_external_action(
        ENTITY_SIGNATURE_REQUEST,
        1,
        "signature_request.signed",
        actor_display_name="חותם חיצוני",
        metadata_json={
            "client_record_id": 1,
            "signer_name": "חותם חיצוני",
            "content_hash": "sha256:test",
            "signed_document_key": "signed/test.pdf",
        },
    )  # no raise


def test_actor_matrix_user_without_performed_by_rolls_back(test_db):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_CLIENT,
            entity_id=1,
            actor_id=None,
            action=entity_action(ENTITY_CLIENT, "updated"),
            actor_display_name=_NAME,
        )
    assert _count(test_db) == 0


def test_actor_matrix_system_with_performed_by_rolls_back(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_CLIENT,
            entity_id=1,
            actor_id=test_user.id,
            action=entity_action(ENTITY_CLIENT, "updated"),
            actor_type="system",
            actor_display_name="מערכת",
        )
    assert _count(test_db) == 0


def test_actor_matrix_external_without_display_rolls_back(test_db):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_SIGNATURE_REQUEST,
            entity_id=1,
            actor_id=None,
            action="signature_request.signed",
            actor_type="external_signer",
            actor_display_name=None,
        )
    assert _count(test_db) == 0


def test_actor_matrix_unknown_actor_type_rolls_back(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_CLIENT,
            entity_id=1,
            actor_id=test_user.id,
            action=entity_action(ENTITY_CLIENT, "updated"),
            actor_type="robot",
            actor_display_name=_NAME,
        )
    assert _count(test_db) == 0


# --------------------------------------------------------------------------- #
# §16 fail-closed write validation
# --------------------------------------------------------------------------- #
def test_forbidden_field_rejected_and_no_row(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_CLIENT,
            entity_id=1,
            actor_id=test_user.id,
            action=entity_action(ENTITY_CLIENT, "updated"),
            new_value={"password_hash": "secret"},
            actor_display_name=_NAME,
        )
    assert _count(test_db) == 0


def test_non_allowlisted_metadata_field_rejected(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_CLIENT,
            entity_id=1,
            actor_id=test_user.id,
            action=entity_action(ENTITY_CLIENT, "updated"),
            metadata_json={"client_record_id": 1, "leaked": "x"},
            actor_display_name=_NAME,
        )
    assert _count(test_db) == 0


def test_business_metadata_requires_client_context(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).record_create(
            "business",
            1,
            test_user.id,
            actor_display_name=_NAME,
            metadata_json={"business_id": 1},
        )
    assert _count(test_db) == 0


def test_signature_created_rejects_client_forensics(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).record_action(
            ENTITY_SIGNATURE_REQUEST,
            1,
            test_user.id,
            "signature_request.created",
            actor_display_name=_NAME,
            metadata_json={
                "client_record_id": 1,
                "signer_name": "חותם",
                "ip_address": "203.0.113.5",
            },
        )
    assert _count(test_db) == 0


def test_signature_signed_requires_hash_evidence(test_db):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).record_external_action(
            ENTITY_SIGNATURE_REQUEST,
            1,
            "signature_request.signed",
            actor_display_name="חותם",
            metadata_json={
                "client_record_id": 1,
                "signer_name": "חותם",
                "signed_document_key": "signed/test.pdf",
            },
        )
    assert _count(test_db) == 0


def test_oversized_payload_rejected(test_db, test_user):
    with pytest.raises(AppError):
        EntityAuditWriter(test_db).append(
            entity_type=ENTITY_CLIENT,
            entity_id=1,
            actor_id=test_user.id,
            action=entity_action(ENTITY_CLIENT, "updated"),
            new_value={"blob": "x" * 40_000},
            actor_display_name=_NAME,
        )
    assert _count(test_db) == 0


# --------------------------------------------------------------------------- #
# Append-only repositories (§17 Option A)
# --------------------------------------------------------------------------- #
def test_audit_repositories_expose_no_mutation_methods(test_db):
    entity_repo = EntityAuditLogRepository(test_db)
    user_repo = UserAuditLogRepository(test_db)
    for repo in (entity_repo, user_repo):
        for method in ("update", "delete", "soft_delete", "hard_delete"):
            assert not hasattr(repo, method), f"{type(repo).__name__} must not expose {method}"


# --------------------------------------------------------------------------- #
# Atomicity (§17): a failed audit write rolls back the domain mutation in the
# same transaction, leaving no orphan domain row.
# --------------------------------------------------------------------------- #
def test_audit_failure_rolls_back_domain_mutation(test_db, test_user, create_client_with_business):
    client_record, business = create_client_with_business(id_number="P2-ATOMIC")
    charge_repo = ChargeRepository(test_db)
    writer = EntityAuditWriter(test_db)

    with pytest.raises(AppError):
        with test_db.begin_nested():  # SAVEPOINT == the domain mutation's transaction
            charge = charge_repo.create(
                client_record_id=client_record.id,
                business_id=business.id,
                amount=100,
                charge_type=ChargeType.CONSULTATION_FEE,
                created_by=test_user.id,
            )
            # forbidden field -> validation raises -> savepoint rolls back
            writer.append(
                entity_type="charge",
                entity_id=charge.id,
                actor_id=test_user.id,
                action="charge.created",
                new_value={"token_hash": "leak"},
                actor_display_name=_NAME,
            )

    # Both the domain row and any audit row are gone — the mutation never committed.
    remaining = test_db.scalars(
        select(Charge).where(Charge.client_record_id == client_record.id)
    ).all()
    assert remaining == []
    assert _count(test_db) == 0


def _count(test_db) -> int:
    return test_db.scalar(select(func.count(EntityAuditLog.id)))
