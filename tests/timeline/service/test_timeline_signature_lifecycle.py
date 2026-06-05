from datetime import UTC, date, datetime

from app.signature_requests.models.signature_request import (
    SignatureAuditEvent,
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.timeline.services.timeline_service import TimelineService
from tests.helpers.identity import seed_business, seed_client_identity


def _business(test_db):
    client = seed_client_identity(test_db, full_name="Timeline Signature", id_number="TSIG100")
    business = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Timeline Signature Business",
        opened_at=date(2026, 1, 1),
    )
    test_db.commit()
    test_db.refresh(business)
    business.client_id = client.id
    return business


def _signature_request(test_db, business, test_user):
    req = SignatureRequest(
        client_record_id=business.client_id,
        business_id=business.id,
        created_by=test_user.id,
        request_type=SignatureRequestType.ANNUAL_REPORT_APPROVAL,
        title="Approve report",
        signer_name="Signer",
        status=SignatureRequestStatus.PENDING_SIGNATURE,
        created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        sent_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
        signed_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
    )
    test_db.add(req)
    test_db.flush()
    return req


def _add_audit(test_db, req, event_type, occurred_at):
    test_db.add(
        SignatureAuditEvent(
            signature_request_id=req.id,
            event_type=event_type,
            actor_type="signer" if event_type in {"signed", "declined"} else "advisor",
            actor_name="Signer",
            notes=f"{event_type} note",
            occurred_at=occurred_at,
        )
    )


def test_signature_lifecycle_events_use_audit_source(test_db, test_user):
    service = TimelineService(test_db)
    business = _business(test_db)
    req = _signature_request(test_db, business, test_user)
    audit_times = {
        "sent": datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        "signed": datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        "declined": datetime(2026, 1, 4, 10, 0, tzinfo=UTC),
        "canceled": datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        "expired": datetime(2026, 1, 6, 10, 0, tzinfo=UTC),
    }
    for event_type, occurred_at in audit_times.items():
        _add_audit(test_db, req, event_type, occurred_at)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)
    by_type = {event["event_type"]: event for event in events}

    assert by_type["signature_request_sent"]["timestamp"] == audit_times["sent"].replace(
        tzinfo=None
    )
    assert by_type["signature_request_signed"]["timestamp"] == audit_times["signed"].replace(
        tzinfo=None
    )
    # decline reason is read from audit_event.notes (snapshot), not the mutable SignatureRequest row
    assert by_type["signature_request_declined"]["metadata"]["reason"] == "declined note"
    assert by_type["signature_request_canceled"]["timestamp"] == audit_times["canceled"].replace(
        tzinfo=None
    )
    assert by_type["signature_request_expired"]["timestamp"] == audit_times["expired"].replace(
        tzinfo=None
    )
    assert "signature_request_created" not in by_type


def test_signature_created_only_request_is_excluded(test_db, test_user):
    service = TimelineService(test_db)
    business = _business(test_db)
    _signature_request(test_db, business, test_user)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "signature_request_created" not in [event["event_type"] for event in events]
