from app.common.enums import AdvancePaymentFrequency


def test_generate_schedule_endpoint_returns_counts(
    client, test_db, advisor_headers, create_client_with_business
):
    _crm_client, business = create_client_with_business(
        full_name="Advance Gen API Client",
        id_number="APGAPI001",
        business_name="Advance Gen Business",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )

    resp = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/generate",
        headers=advisor_headers,
        json={"business_id": business.id, "year": 2026, "reference_date": "2025-12-31"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["created"] == 12
    assert payload["skipped"] == 0


def test_generate_schedule_reports_stale_cadence_then_clears_it_on_confirm(
    client, test_db, advisor_headers, create_client_with_business
):
    from app.legal_entities.models.legal_entity import LegalEntity
    from app.utils.time_utils import israel_today

    future_year = israel_today().year + 1
    _crm_client, business = create_client_with_business(
        full_name="Advance Gen API Client",
        id_number="APGAPI001",
        business_name="Advance Gen Business",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )
    url = f"/api/v1/clients/{business.client_record_id}/advance-payments/generate"

    first = client.post(url, headers=advisor_headers, json={"year": future_year})
    assert first.json()["created"] == 12

    legal_entity = test_db.get(LegalEntity, business.legal_entity_id)
    legal_entity.advance_payment_frequency = AdvancePaymentFrequency.BIMONTHLY
    test_db.commit()

    reported = client.post(url, headers=advisor_headers, json={"year": future_year})
    assert reported.status_code == 200
    body = reported.json()
    assert body["created"] == 0
    assert body["stale_cadence"] == {"removed": 0, "pending": 12, "settled": 0}

    confirmed = client.post(
        url,
        headers=advisor_headers,
        json={"year": future_year, "cleanup_stale_cadence": True},
    )
    assert confirmed.status_code == 200
    confirmed_body = confirmed.json()
    assert confirmed_body["created"] == 6
    assert confirmed_body["stale_cadence"] == {"removed": 12, "pending": 0, "settled": 0}


def test_generate_schedule_endpoint_is_advisor_only(
    client, test_db, secretary_headers, create_client_with_business
):
    _crm_client, business = create_client_with_business(
        full_name="Advance Gen API Client",
        id_number="APGAPI001",
        business_name="Advance Gen Business",
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
    )

    resp = client.post(
        f"/api/v1/clients/{business.client_record_id}/advance-payments/generate",
        headers=secretary_headers,
        json={"business_id": business.id, "year": 2026},
    )

    assert resp.status_code == 403
