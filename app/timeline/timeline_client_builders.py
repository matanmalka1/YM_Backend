from app.audit.audit_constants import (
    ENTITY_ANNUAL_REPORT,
    ENTITY_BUSINESS,
    ENTITY_CHARGE,
    ENTITY_CLIENT,
)
from app.timeline.timeline_labels import (
    DOCUMENT_TYPE_HE,
    SIGNATURE_REQUEST_TYPE_HE,
)

# One timeline event_type per audited entity. The frontend renders the diff from
# the raw audit fields in metadata via the existing audit formatter — no value
# formatting duplicated here.
_ENTITY_CHANGE_EVENT_TYPE = {
    ENTITY_CLIENT: "client_record_changed",
    ENTITY_BUSINESS: "business_changed",
    ENTITY_CHARGE: "charge_changed",
    ENTITY_ANNUAL_REPORT: "annual_report_changed",
}

# Search-friendly Hebrew noun per entity (titles are built on the frontend).
_ENTITY_CHANGE_NOUN = {
    ENTITY_CLIENT: "שינוי בפרטי לקוח",
    ENTITY_BUSINESS: "שינוי בפרטי עסק",
    ENTITY_CHARGE: "שינוי בחיוב",
    ENTITY_ANNUAL_REPORT: "שינוי בדוח שנתי",
}


def entity_audit_changed_event(audit_log, performer_name: str | None) -> dict:
    """Adapt an EntityAuditLog row into a timeline change event.

    Supports client / business / charge / annual_report. Carries the raw audit
    fields in metadata so the diff renders through the shared audit formatter.
    """
    entity_type = audit_log.entity_type
    return {
        "event_type": _ENTITY_CHANGE_EVENT_TYPE[entity_type],
        "timestamp": audit_log.performed_at,
        "binder_id": None,
        "charge_id": audit_log.entity_id if entity_type == ENTITY_CHARGE else None,
        "description": _ENTITY_CHANGE_NOUN[entity_type],
        "metadata": {
            "entity_type": entity_type,
            "entity_id": audit_log.entity_id,
            "change_action": audit_log.action,
            "change_old": audit_log.old_value,
            "change_new": audit_log.new_value,
            "note": audit_log.note,
            "performed_by_name": performer_name,
        },
    }


def client_created_event(client) -> dict:
    client_name = getattr(client, "full_name", None) or getattr(client, "official_name", "")
    entity_type = getattr(client, "entity_type", None)
    entity_type_value = getattr(entity_type, "value", entity_type)
    return {
        "event_type": "client_created",
        "timestamp": client.created_at,
        "binder_id": None,
        "charge_id": None,
        "description": f"לקוח נוצר: {client_name}",
        "metadata": {"entity_type": entity_type_value},
    }


def document_uploaded_event(document) -> dict:
    doc_type = (
        document.document_type.value
        if hasattr(document.document_type, "value")
        else document.document_type
    )
    type_he = DOCUMENT_TYPE_HE.get(doc_type, doc_type)
    return {
        "event_type": "document_uploaded",
        "timestamp": document.uploaded_at,
        "binder_id": None,
        "charge_id": None,
        "description": f"מסמך הועלה: {type_he}",
        "metadata": {"document_type": doc_type},
    }


def signature_request_lifecycle_event(sig_request, audit_event) -> dict:
    event_type_map = {
        "sent": "signature_request_sent",
        "signed": "signature_request_signed",
        "declined": "signature_request_declined",
        "canceled": "signature_request_canceled",
        "expired": "signature_request_expired",
    }
    label_map = {
        "sent": "בקשת חתימה נשלחה",
        "signed": "מסמך נחתם",
        "declined": "חתימה נדחתה",
        "canceled": "בקשת חתימה בוטלה",
        "expired": "בקשת חתימה פגה",
    }
    type_he = SIGNATURE_REQUEST_TYPE_HE.get(
        sig_request.request_type.value, sig_request.request_type.value
    )
    audit_type = audit_event.event_type
    return {
        "event_type": event_type_map[audit_type],
        "timestamp": audit_event.occurred_at,
        "binder_id": None,
        "charge_id": None,
        "description": f"{label_map[audit_type]}: {type_he}",
        "metadata": {
            "signature_request_id": sig_request.id,
            "request_type": sig_request.request_type.value,
            "status": sig_request.status.value,
            "annual_report_id": sig_request.annual_report_id,
            "document_id": sig_request.document_id,
            "signer_name": sig_request.signer_name,
            "reason": audit_event.notes if audit_type == "declined" else None,
            "notes": audit_event.notes,
        },
    }
