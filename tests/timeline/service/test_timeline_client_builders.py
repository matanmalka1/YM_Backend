from datetime import datetime
from types import SimpleNamespace

from app.common.enums import EntityType
from app.documents.permanent_documents.models.permanent_document import PermanentDocumentType
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.timeline.services.timeline_client_builders import (
    client_created_event,
    document_uploaded_event,
    signature_request_lifecycle_event,
)


def test_client_builder_events():
    client = SimpleNamespace(
        full_name="Client Builder",
        created_at=datetime(2026, 1, 1, 8, 0),
        updated_at=datetime(2026, 1, 2, 8, 0),
        entity_type=EntityType.COMPANY_LTD,
    )

    created = client_created_event(client)
    assert created["event_type"] == "client_created"
    assert created["description"] == "לקוח נוצר: Client Builder"
    assert created["metadata"] == {"entity_type": "company_ltd"}
    assert "actions" not in created
    assert "available_actions" not in created


def test_document_and_signature_lifecycle_builder_events():
    document = SimpleNamespace(
        document_type=PermanentDocumentType.ID_COPY,
        uploaded_at=datetime(2026, 1, 5, 11, 0),
    )
    signature_request = SimpleNamespace(
        id=15,
        request_type=SignatureRequestType.ANNUAL_REPORT_APPROVAL,
        created_at=datetime(2026, 1, 6, 12, 0),
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        annual_report_id=8,
        document_id=9,
        signer_name="Signer",
        decline_reason=None,
    )
    audit_event = SimpleNamespace(
        event_type="sent",
        occurred_at=datetime(2026, 1, 6, 13, 0),
        notes="נשלח",
    )

    document_event = document_uploaded_event(document)
    assert document_event["event_type"] == "document_uploaded"
    assert document_event["metadata"] == {"document_type": "id_copy"}
    assert "actions" not in document_event
    assert "available_actions" not in document_event

    signature_event = signature_request_lifecycle_event(signature_request, audit_event)
    assert signature_event["event_type"] == "signature_request_sent"
    assert signature_event["timestamp"] == datetime(2026, 1, 6, 13, 0)
    assert signature_event["metadata"] == {
        "signature_request_id": 15,
        "request_type": "annual_report_approval",
        "status": "pending_signature",
        "annual_report_id": 8,
        "document_id": 9,
        "signer_name": "Signer",
        "reason": None,
        "notes": "נשלח",
    }
    assert "actions" not in signature_event
    assert "available_actions" not in signature_event
