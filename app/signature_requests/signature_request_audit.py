"""Generic audit helpers for signature-request lifecycle evidence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.audit.audit_constants import (
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_CREATED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
    ACTION_SIGNATURE_REQUEST_VIEWED,
    ENTITY_SIGNATURE_REQUEST,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.audit.services.audit_entity_audit_writer_service import EntityAuditWriter
from app.signature_requests.models.signature_request import SignatureRequest

SIGNATURE_REQUEST_SYSTEM_ACTOR = "מערכת חתימות דיגיטליות"


def signature_request_metadata(
    req: SignatureRequest,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    include_signature_evidence: bool = False,
    reason: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "client_record_id": req.client_record_id,
        "signer_name": req.signer_name,
    }
    if req.signer_email:
        metadata["signer_email"] = req.signer_email
    if req.business_id is not None:
        metadata["business_id"] = req.business_id
    if req.document_id is not None:
        metadata["document_id"] = req.document_id
    if ip_address:
        metadata["ip_address"] = ip_address
    if user_agent:
        metadata["user_agent"] = user_agent
    if include_signature_evidence:
        if req.content_hash:
            metadata["content_hash"] = req.content_hash
        else:
            metadata["content_hash_missing"] = True
        if req.signed_document_key:
            metadata["signed_document_key"] = req.signed_document_key
    if reason:
        metadata["reason"] = reason
    return metadata


def record_signature_user_action(
    db: Session,
    req: SignatureRequest,
    *,
    actor_id: int,
    actor_display_name: str,
    action: str,
    note: str | None = None,
    reason: str | None = None,
    performed_at: datetime | None = None,
) -> EntityAuditLog:
    row = EntityAuditWriter(db).record_action(
        ENTITY_SIGNATURE_REQUEST,
        req.id,
        actor_id,
        action,
        note=note,
        actor_display_name=actor_display_name,
        metadata_json=signature_request_metadata(req, reason=reason),
    )
    if performed_at is not None:
        row.performed_at = performed_at
        db.flush()
    return row


def record_signature_external_action(
    db: Session,
    req: SignatureRequest,
    *,
    action: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    note: str | None = None,
    reason: str | None = None,
    performed_at: datetime | None = None,
) -> EntityAuditLog:
    row = EntityAuditWriter(db).record_external_action(
        ENTITY_SIGNATURE_REQUEST,
        req.id,
        action,
        actor_display_name=req.signer_name,
        note=note,
        metadata_json=signature_request_metadata(
            req,
            ip_address=ip_address,
            user_agent=user_agent,
            include_signature_evidence=action == ACTION_SIGNATURE_REQUEST_SIGNED,
            reason=reason,
        ),
    )
    if performed_at is not None:
        row.performed_at = performed_at
        db.flush()
    return row


def record_signature_system_action(
    db: Session,
    req: SignatureRequest,
    *,
    action: str,
    note: str | None = None,
    reason: str | None = None,
    performed_at: datetime | None = None,
) -> EntityAuditLog:
    row = EntityAuditWriter(db).record_action(
        ENTITY_SIGNATURE_REQUEST,
        req.id,
        None,
        action,
        note=note,
        actor_type="system",
        actor_display_name=SIGNATURE_REQUEST_SYSTEM_ACTOR,
        metadata_json=signature_request_metadata(req, reason=reason),
    )
    if performed_at is not None:
        row.performed_at = performed_at
        db.flush()
    return row


__all__ = [
    "ACTION_SIGNATURE_REQUEST_CANCELED",
    "ACTION_SIGNATURE_REQUEST_CREATED",
    "ACTION_SIGNATURE_REQUEST_DECLINED",
    "ACTION_SIGNATURE_REQUEST_EXPIRED",
    "ACTION_SIGNATURE_REQUEST_SENT",
    "ACTION_SIGNATURE_REQUEST_SIGNED",
    "ACTION_SIGNATURE_REQUEST_VIEWED",
    "SIGNATURE_REQUEST_SYSTEM_ACTOR",
    "record_signature_external_action",
    "record_signature_system_action",
    "record_signature_user_action",
    "signature_request_metadata",
]
