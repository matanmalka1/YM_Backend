from datetime import date

from app.audit.audit_constants import (
    ACTION_SIGNATURE_REQUEST_DECLINED,
    ACTION_SIGNATURE_REQUEST_VIEWED,
)
from app.businesses.models.business import Business
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)


def _business(create_client_with_business) -> Business:
    _client, business = create_client_with_business(
        full_name="Signature Client",
        id_number="999999991",
        email="client@example.com",
        phone="050-1234567",
        business_name="Signature Business",
        opened_at=date(2026, 1, 1),
    )
    return business


def test_signature_request_full_sign_flow(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business)

    create_resp = client.post(
        "/api/v1/signature-requests",
        headers=advisor_headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": "Engagement Letter",
            "description": "Please approve",
            "signer_name": "Client Rep",
            "content_to_hash": "hash-me",
        },
    )
    assert create_resp.status_code == 201
    sent = create_resp.json()
    request_id = sent["id"]
    token = sent["signing_token"]
    assert sent["status"] == "pending_signature"
    assert sent["signing_url_hint"] == f"/sign/{token}"

    view_resp = client.get(f"/sign/{token}")
    assert view_resp.status_code == 200
    assert view_resp.json()["status"] == "pending_signature"

    approve_resp = client.post(f"/sign/{token}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "signed"

    detail_resp = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "signed"
    assert "signing_token" not in detail
    assert "signing_url_hint" not in detail
    # Audit trail should include created, sent, viewed, signed
    actions = [e["action"] for e in detail["audit_trail"]]
    assert {
        "signature_request.created",
        "signature_request.sent",
        "signature_request.viewed",
        "signature_request.signed",
    } <= set(actions)
    signed_event = next(
        e for e in detail["audit_trail"] if e["action"] == "signature_request.signed"
    )
    assert signed_event["actor_type"] == "external_signer"
    assert signed_event["actor_display_name"] == "Client Rep"
    assert signed_event["content_hash"]
    assert signed_event["content_hash_missing"] is None


def test_signature_request_decline_records_reason(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business)

    create_resp = client.post(
        "/api/v1/signature-requests",
        headers=advisor_headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": "Decline Test",
            "signer_name": "Decliner",
        },
    )
    sent = create_resp.json()
    request_id = sent["id"]
    token = sent["signing_token"]

    decline_resp = client.post(
        f"/sign/{token}/decline",
        json={"reason": "I disagree"},
    )
    assert decline_resp.status_code == 200
    assert decline_resp.json()["status"] == "declined"

    repo = SignatureRequestRepository(test_db)
    stored = repo.get_by_id(request_id)
    assert stored.status.value == "declined"
    assert stored.signing_token is None
    # Decline reason persisted
    assert stored.decline_reason == "I disagree"


def test_signature_request_signed_without_hash_records_missing_hash(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business)
    create_resp = client.post(
        "/api/v1/signature-requests",
        headers=advisor_headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": "No Hash Signature",
            "signer_name": "No Hash Signer",
        },
    )
    payload = create_resp.json()

    approve_resp = client.post(f"/sign/{payload['signing_token']}/approve")
    assert approve_resp.status_code == 200

    detail_resp = client.get(f"/api/v1/signature-requests/{payload['id']}", headers=advisor_headers)
    signed_event = next(
        event
        for event in detail_resp.json()["audit_trail"]
        if event["action"] == "signature_request.signed"
    )
    assert signed_event["content_hash"] is None
    assert signed_event["content_hash_missing"] is True


def test_signature_request_viewed_and_declined_forensics_visible_to_both_roles(
    client, test_db, advisor_headers, secretary_headers, create_client_with_business
):
    business = _business(create_client_with_business)
    create_resp = client.post(
        "/api/v1/signature-requests",
        headers=advisor_headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": "Forensics",
            "signer_name": "Forensic Signer",
        },
    )
    payload = create_resp.json()

    view_resp = client.get(
        f"/sign/{payload['signing_token']}",
        headers={"user-agent": "signature-view-test/1.0"},
    )
    assert view_resp.status_code == 200
    decline_resp = client.post(
        f"/sign/{payload['signing_token']}/decline",
        headers={"user-agent": "signature-decline-test/1.0"},
        json={"reason": "Need changes"},
    )
    assert decline_resp.status_code == 200

    advisor_detail = client.get(
        f"/api/v1/signature-requests/{payload['id']}", headers=advisor_headers
    ).json()
    secretary_detail = client.get(
        f"/api/v1/signature-requests/{payload['id']}", headers=secretary_headers
    ).json()

    for detail in (advisor_detail, secretary_detail):
        viewed = next(
            event
            for event in detail["audit_trail"]
            if event["action"] == ACTION_SIGNATURE_REQUEST_VIEWED
        )
        declined = next(
            event
            for event in detail["audit_trail"]
            if event["action"] == ACTION_SIGNATURE_REQUEST_DECLINED
        )
        assert viewed["actor_type"] == "external_signer"
        assert viewed["actor_display_name"] == "Forensic Signer"
        assert viewed["ip_address"] == "testclient"
        assert viewed["user_agent"] == "signature-view-test/1.0"
        assert declined["ip_address"] == "testclient"
        assert declined["user_agent"] == "signature-decline-test/1.0"
        assert declined["reason"] == "Need changes"


def test_signature_request_audit_ordering_embedded_chronological_generic_newest_first(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business)
    resp = client.post(
        "/api/v1/signature-requests",
        headers=advisor_headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": "Ordering",
            "signer_name": "Signer",
        },
    )
    request_id = resp.json()["id"]

    embedded = client.get(
        f"/api/v1/signature-requests/{request_id}", headers=advisor_headers
    ).json()
    assert [event["action"] for event in embedded["audit_trail"]] == [
        "signature_request.created",
        "signature_request.sent",
    ]

    generic = client.get(
        f"/api/v1/audit/signature_request/{request_id}", headers=advisor_headers
    ).json()
    assert [event["action"] for event in generic["items"]] == [
        "signature_request.sent",
        "signature_request.created",
    ]


def test_list_pending_returns_only_pending(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business)

    for i in range(2):
        client.post(
            "/api/v1/signature-requests",
            headers=advisor_headers,
            json={
                "business_id": business.id,
                "client_record_id": business.client_id,
                "request_type": "custom",
                "title": f"Pending {i}",
                "signer_name": "Signer",
            },
        )

    pending_resp = client.get(
        "/api/v1/signature-requests/pending?page=1&page_size=10",
        headers=advisor_headers,
    )
    assert pending_resp.status_code == 200
    payload = pending_resp.json()
    assert payload["total"] == 2
    assert all(item["status"] == "pending_signature" for item in payload["items"])
    assert all("signing_token" not in item for item in payload["items"])
    assert all("signing_url_hint" not in item for item in payload["items"])


def test_create_signature_request_sends_immediately(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business)

    resp = client.post(
        "/api/v1/signature-requests",
        headers=advisor_headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": "Create and send",
            "signer_name": "Signer",
            "expiry_days": 7,
        },
    )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["status"] == "pending_signature"
    assert payload["signing_token"]
    assert payload["signing_url_hint"] == f"/sign/{payload['signing_token']}"

    detail = client.get(f"/api/v1/signature-requests/{payload['id']}", headers=advisor_headers)
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert "signing_token" not in detail_payload
    assert "signing_url_hint" not in detail_payload
    actions = [event["action"] for event in detail_payload["audit_trail"]]
    assert actions == ["signature_request.created", "signature_request.sent"]
    assert detail_payload["audit_trail"][0]["actor_type"] == "user"
    assert detail_payload["audit_trail"][0]["signer_name"] == "Signer"


def test_invalid_token_returns_error_on_sign(client):
    # Valid-format (>=32 chars) but non-existent token: passes path validation,
    # then fails the token lookup with TOKEN_INVALID.
    resp = client.post(f"/sign/{'z' * 40}/approve")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SIGNATURE_REQUEST.TOKEN_INVALID"
