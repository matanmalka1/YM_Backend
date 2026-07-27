from datetime import date

from app.businesses.models.business import Business
from app.signature_requests.models.signature_request import SignatureRequestStatus
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)


def _business(create_client_with_business, suffix: str) -> Business:
    _client, business = create_client_with_business(
        full_name=f"Signature List Client {suffix}",
        id_number=f"SIG-API-{suffix}",
        email=f"sig{suffix}@example.com",
        business_name=f"Signature List Business {suffix}",
        opened_at=date(2026, 1, 1),
    )
    return business


def _create_signature_request(api_client, headers, business: Business, title: str) -> int:
    resp = api_client.post(
        "/api/v1/signature-requests",
        headers=headers,
        json={
            "business_id": business.id,
            "client_record_id": business.client_id,
            "request_type": "custom",
            "title": title,
            "signer_name": "Signer",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_cancel_signature_request(client, test_db, advisor_headers, create_client_with_business):
    business = _business(create_client_with_business, "A")
    request_id = _create_signature_request(client, advisor_headers, business, "Cancelable")

    cancel_resp = client.post(
        f"/api/v1/clients/{business.client_id}/signature-requests/{request_id}/cancel",
        headers=advisor_headers,
        json={"reason": "Client asked to stop"},
    )

    assert cancel_resp.status_code == 200
    cancel_payload = cancel_resp.json()
    assert cancel_payload["status"] == "canceled"
    assert "signing_token" not in cancel_payload
    assert "signing_url_hint" not in cancel_payload

    detail = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers)
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert "signing_token" not in detail_payload
    assert "signing_url_hint" not in detail_payload
    events = detail_payload["audit_trail"]
    actions = [e["action"] for e in events]
    assert "signature_request.canceled" in actions
    canceled_event = next(e for e in events if e["action"] == "signature_request.canceled")
    assert canceled_event["reason"] == "Client asked to stop"


def test_list_signature_requests_by_client_with_status_filter(
    client, test_db, advisor_headers, create_client_with_business
):
    business_a = _business(create_client_with_business, "B")
    business_b = _business(create_client_with_business, "C")

    req_a_pending = _create_signature_request(client, advisor_headers, business_a, "Pending A")

    req_a_canceled = _create_signature_request(client, advisor_headers, business_a, "Canceled A")
    client.post(
        f"/api/v1/clients/{business_a.client_id}/signature-requests/{req_a_canceled}/cancel",
        headers=advisor_headers,
        json={"reason": "No longer needed"},
    )
    _create_signature_request(client, advisor_headers, business_b, "Other client")

    all_resp = client.get(
        f"/api/v1/clients/{business_a.client_id}/signature-requests?page=1&page_size=10",
        headers=advisor_headers,
    )
    assert all_resp.status_code == 200
    assert all_resp.json()["total"] == 2
    all_payload = all_resp.json()
    returned_ids = {item["id"] for item in all_payload["items"]}
    assert returned_ids == {req_a_pending, req_a_canceled}
    assert all("signing_token" not in item for item in all_payload["items"])
    assert all("signing_url_hint" not in item for item in all_payload["items"])

    pending_resp = client.get(
        f"/api/v1/clients/{business_a.client_id}/signature-requests?status=pending_signature",
        headers=advisor_headers,
    )
    assert pending_resp.status_code == 200
    pending_payload = pending_resp.json()
    assert pending_payload["total"] == 1
    assert pending_payload["items"][0]["id"] == req_a_pending
    assert "signing_token" not in pending_payload["items"][0]
    assert "signing_url_hint" not in pending_payload["items"][0]


def test_get_signature_request_not_found_returns_404(client, advisor_headers):
    resp = client.get("/api/v1/signature-requests/999999", headers=advisor_headers)

    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "בקשת חתימה 999999 לא נמצאה"
    assert resp.json()["error"]["code"] == "SIGNATURE_REQUEST.NOT_FOUND"


def test_cancel_signature_request_rejects_mismatched_client_scope(
    client, test_db, advisor_headers, create_client_with_business
):
    business_a = _business(create_client_with_business, "D")
    business_b = _business(create_client_with_business, "E")
    request_id = _create_signature_request(client, advisor_headers, business_a, "Scoped")

    resp = client.post(
        f"/api/v1/clients/{business_b.client_id}/signature-requests/{request_id}/cancel",
        headers=advisor_headers,
        json={},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SIGNATURE_REQUEST.NOT_FOUND"
    detail = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers)
    assert detail.json()["status"] == "pending_signature"


def test_cancel_signature_request_rejects_terminal_status_as_not_found(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business, "G")
    request_id = _create_signature_request(client, advisor_headers, business, "Signed")
    SignatureRequestRepository(test_db).update(request_id, status=SignatureRequestStatus.SIGNED)

    resp = client.post(
        f"/api/v1/clients/{business.client_id}/signature-requests/{request_id}/cancel",
        headers=advisor_headers,
        json={},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SIGNATURE_REQUEST.NOT_FOUND"
    detail = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers)
    assert detail.json()["status"] == "signed"


def test_bare_cancel_route_is_not_available(
    client, test_db, advisor_headers, create_client_with_business
):
    business = _business(create_client_with_business, "F")
    request_id = _create_signature_request(client, advisor_headers, business, "No bare route")

    resp = client.post(
        f"/api/v1/signature-requests/{request_id}/cancel",
        headers=advisor_headers,
        json={},
    )

    assert resp.status_code == 404
