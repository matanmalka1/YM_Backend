from app.timeline.timeline_labels import (
    DOCUMENT_TYPE_HE,
    SIGNATURE_REQUEST_TYPE_HE,
)


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
