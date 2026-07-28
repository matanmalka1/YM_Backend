"""API-level validation of the per-obligation-type liability ranges.

The database CheckConstraints guarantee the invariant; these schemas exist to turn
a violation into a readable 422 before it gets that far, and to reject a range for
an obligation type the client does not have.
"""

import copy
from datetime import date

import pytest

_CREATE_PAYLOAD = {
    "client": {
        "full_name": "Liability Range Client",
        "id_number": "514713288",
        "id_number_type": "corporation",
        "entity_type": "company_ltd",
        "phone": "050-0000001",
        "email": "liability@example.com",
        "address_street": "Test St",
        "address_building_number": "1",
        "address_apartment": "1",
        "address_city": "Tel Aviv",
        "address_zip_code": "0000001",
        "vat_reporting_frequency": "monthly",
        "advance_payment_frequency": "monthly",
        "advance_rate": "5.0",
        "accountant_id": None,
    },
    "business": {
        "business_name": "Liability Business",
        "opened_at": str(date.today()),
    },
}


def _payload(**client_overrides):
    payload = copy.deepcopy(_CREATE_PAYLOAD)
    payload["client"].update(client_overrides)
    return payload


class TestCreateValidation:
    def test_accepts_a_well_ordered_range(self, client, advisor_headers):
        resp = client.post(
            "/api/v1/clients",
            headers=advisor_headers,
            json=_payload(vat_liable_from="2026-06-01", vat_liable_to="2026-12-31"),
        )
        assert resp.status_code == 201, resp.json()

    def test_accepts_an_open_ended_range(self, client, advisor_headers):
        resp = client.post(
            "/api/v1/clients",
            headers=advisor_headers,
            json=_payload(vat_liable_from="2026-06-01"),
        )
        assert resp.status_code == 201, resp.json()

    @pytest.mark.parametrize(
        ("start_field", "end_field"),
        [
            ("vat_liable_from", "vat_liable_to"),
            ("advance_liable_from", "advance_liable_to"),
            ("annual_liable_from", "annual_liable_to"),
        ],
    )
    def test_rejects_an_inverted_range(self, client, advisor_headers, start_field, end_field):
        resp = client.post(
            "/api/v1/clients",
            headers=advisor_headers,
            json=_payload(**{start_field: "2026-08-01", end_field: "2026-03-01"}),
        )
        assert resp.status_code == 422, resp.json()

    def test_rejects_a_vat_range_on_a_client_that_does_not_report_vat(
        self, client, advisor_headers
    ):
        """osek_patur files no VAT return, so a VAT liability range is meaningless."""
        payload = _payload(vat_liable_from="2026-06-01")
        payload["client"]["entity_type"] = "osek_patur"
        payload["client"]["id_number"] = "123456782"
        payload["client"]["id_number_type"] = "individual"
        payload["client"].pop("vat_reporting_frequency")

        resp = client.post("/api/v1/clients", headers=advisor_headers, json=payload)

        assert resp.status_code == 422, resp.json()


class TestPreviewAgreesWithCreate:
    def test_preview_applies_the_same_ranges(self, client, advisor_headers):
        """A preview that ignored the ranges would promise a different number of
        obligations than the create produces."""
        unbounded = client.post(
            "/api/v1/clients/preview-impact",
            headers=advisor_headers,
            json={
                "client": {
                    "entity_type": "osek_murshe",
                    "vat_reporting_frequency": "monthly",
                    "advance_payment_frequency": "monthly",
                }
            },
        )
        narrowed = client.post(
            "/api/v1/clients/preview-impact",
            headers=advisor_headers,
            json={
                "client": {
                    "entity_type": "osek_murshe",
                    "vat_reporting_frequency": "monthly",
                    "advance_payment_frequency": "monthly",
                    "vat_liable_from": f"{date.today().year}-12-01",
                }
            },
        )
        assert unbounded.status_code == 200
        assert narrowed.status_code == 200

        def vat_count(resp):
            return {i["label"]: i["count"] for i in resp.json()["items"]}.get('דוחות מע"מ', 0)

        assert vat_count(narrowed) < vat_count(unbounded)

    def test_preview_rejects_an_inverted_range(self, client, advisor_headers):
        resp = client.post(
            "/api/v1/clients/preview-impact",
            headers=advisor_headers,
            json={
                "client": {
                    "entity_type": "osek_murshe",
                    "vat_reporting_frequency": "monthly",
                    "vat_liable_from": "2026-08-01",
                    "vat_liable_to": "2026-03-01",
                }
            },
        )
        assert resp.status_code == 422, resp.json()
