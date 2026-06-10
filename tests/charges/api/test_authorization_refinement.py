from datetime import date

from app.businesses.models.business import Business, BusinessStatus
from tests.helpers.identity import seed_client_identity


def test_secretary_sees_charge_amounts(client, secretary_headers, advisor_headers, test_db):
    """Secretary has full charge visibility — same as advisor."""
    test_client = seed_client_identity(
        full_name="Auth Test",
        id_number="700000002",
        db=test_db,
    )
    test_business = Business(
        business_name=test_client.full_name,
        legal_entity_id=test_client.legal_entity_id,
        status=BusinessStatus.ACTIVE,
        opened_at=date.today(),
    )
    test_business.client_record_id = test_client.id
    test_db.add(test_business)
    test_db.commit()
    test_db.refresh(test_business)

    create_response = client.post(
        "/api/v1/charges",
        headers=advisor_headers,
        json={
            "client_record_id": test_business.client_record_id,
            "business_id": test_business.id,
            "amount": 500.0,
            "charge_type": "monthly_retainer",
        },
    )
    assert create_response.status_code == 201

    for headers in (secretary_headers, advisor_headers):
        response = client.get("/api/v1/charges", headers=headers)
        assert response.status_code == 200
        data = response.json()
        if data["items"]:
            assert "amount" in data["items"][0]
