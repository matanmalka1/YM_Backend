from datetime import UTC, date, datetime

from app.audit.audit_constants import (
    ACTION_SIGNATURE_REQUEST_CANCELED,
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_EXPIRED,
    ACTION_SIGNATURE_REQUEST_SENT,
    ACTION_SIGNATURE_REQUEST_SIGNED,
)
from app.signature_requests.models.signature_request import (
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.signature_requests.signature_request_audit import (
    record_signature_external_action,
    record_signature_system_action,
    record_signature_user_action,
)
from app.timeline.services.timeline_service import TimelineService


def _business(create_client_with_business):
    _, business = create_client_with_business(
        full_name="Timeline Signature",
        id_number="TSIG100",
        business_name="Timeline Signature Business",
        opened_at=date(2026, 1, 1),
    )
    return business


def _signature_request(signature_request_factory, business, test_user):
    return signature_request_factory(
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


def _add_audit(test_db, req, action, occurred_at):
    if action in {ACTION_SIGNATURE_REQUEST_SIGNED, ACTION_SIGNATURE_REQUEST_DECLINED}:
        record_signature_external_action(
            test_db,
            req,
            action=action,
            note=f"{action.rsplit('.', 1)[1]} note",
            performed_at=occurred_at,
        )
        return
    if action == ACTION_SIGNATURE_REQUEST_EXPIRED:
        record_signature_system_action(
            test_db,
            req,
            action=action,
            note="expired note",
            reason="expired note",
            performed_at=occurred_at,
        )
        return
    record_signature_user_action(
        test_db,
        req,
        actor_id=req.created_by,
        actor_display_name="Advisor",
        action=action,
        note=f"{action.rsplit('.', 1)[1]} note",
        performed_at=occurred_at,
    )


def test_signature_lifecycle_events_use_audit_source(
    test_db, test_user, create_client_with_business, signature_request_factory
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    req = _signature_request(signature_request_factory, business, test_user)
    audit_times = {
        ACTION_SIGNATURE_REQUEST_SENT: datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        ACTION_SIGNATURE_REQUEST_SIGNED: datetime(2026, 1, 3, 10, 0, tzinfo=UTC),
        ACTION_SIGNATURE_REQUEST_DECLINED: datetime(2026, 1, 4, 10, 0, tzinfo=UTC),
        ACTION_SIGNATURE_REQUEST_CANCELED: datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        ACTION_SIGNATURE_REQUEST_EXPIRED: datetime(2026, 1, 6, 10, 0, tzinfo=UTC),
    }
    for action, occurred_at in audit_times.items():
        _add_audit(test_db, req, action, occurred_at)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)
    by_type = {event["event_type"]: event for event in events}

    assert by_type["signature_request_sent"]["timestamp"] == audit_times[
        ACTION_SIGNATURE_REQUEST_SENT
    ].replace(tzinfo=None)
    assert by_type["signature_request_signed"]["timestamp"] == audit_times[
        ACTION_SIGNATURE_REQUEST_SIGNED
    ].replace(tzinfo=None)
    # decline reason is read from audit_event.notes (snapshot), not the mutable SignatureRequest row
    assert by_type["signature_request_declined"]["metadata"]["reason"] == "declined note"
    assert by_type["signature_request_canceled"]["timestamp"] == audit_times[
        ACTION_SIGNATURE_REQUEST_CANCELED
    ].replace(tzinfo=None)
    assert by_type["signature_request_expired"]["timestamp"] == audit_times[
        ACTION_SIGNATURE_REQUEST_EXPIRED
    ].replace(tzinfo=None)
    assert "signature_request_created" not in by_type


def test_signature_created_only_request_is_excluded(
    test_db, test_user, create_client_with_business, signature_request_factory
):
    service = TimelineService(test_db)
    business = _business(create_client_with_business)
    _signature_request(signature_request_factory, business, test_user)
    test_db.commit()

    events, _ = service.get_client_timeline(business.client_id, page=1, page_size=50)

    assert "signature_request_created" not in [event["event_type"] for event in events]
