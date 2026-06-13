"""issue #46 — SignatureRequestResponse.updated_at.

Set only on real mutation of the request row (here: cancel). The row-level
updated_at is independent of the append-only SignatureAuditEvent trail,
which stays the detailed source of truth. Never faked from created_at.
"""

from datetime import date

from app.businesses.models.business import Business
from tests.helpers.identity import seed_client_with_business


def _business(db, suffix: str) -> Business:
    _client, business = seed_client_with_business(
        db,
        full_name=f"Sig UpdatedAt {suffix}",
        id_number=f"SIG-UA-{suffix}",
        email=f"sigua{suffix}@example.com",
        business_name=f"Sig UpdatedAt Business {suffix}",
        opened_at=date(2026, 1, 1),
    )
    db.commit()
    return business


def _create(api_client, headers, business: Business, title: str) -> int:
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


def test_updated_at_present_on_create_response(client, test_db, advisor_headers):
    business = _business(test_db, "A")
    request_id = _create(client, advisor_headers, business, "Has Field")

    detail = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers).json()
    assert "updated_at" in detail


def test_cancel_bumps_updated_at(client, test_db, advisor_headers):
    business = _business(test_db, "B")
    request_id = _create(client, advisor_headers, business, "Cancelable")

    before = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers).json()

    cancel = client.post(
        f"/api/v1/clients/{business.client_id}/signature-requests/{request_id}/cancel",
        headers=advisor_headers,
        json={"reason": "stop"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "canceled"

    after = client.get(f"/api/v1/signature-requests/{request_id}", headers=advisor_headers).json()
    assert after["updated_at"] is not None
    assert after["updated_at"] >= after["created_at"]
    if before["updated_at"] is not None:
        assert after["updated_at"] >= before["updated_at"]


def test_column_has_no_default_null_on_bare_insert(test_db):
    """Guard the no-fake rule: a pure insert leaves updated_at NULL (no default=)."""
    from app.signature_requests.models.signature_request import (
        SignatureRequest,
        SignatureRequestType,
    )

    req = SignatureRequest(
        client_record_id=1,
        created_by=1,
        request_type=SignatureRequestType.CUSTOM,
        title="Bare",
        signer_name="Signer",
    )
    test_db.add(req)
    test_db.flush()
    assert req.updated_at is None
