"""
Tests for POST/GET /api/v1/clients.
Uses valid Israeli ID numbers (pass Luhn checksum).
"""

from sqlalchemy import func, select

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from tests.clients.helpers import create_client_via_api


def test_authenticated_client_creation(client, auth_token):
    """Authenticated user can create a client."""
    response = create_client_via_api(
        client,
        {"Authorization": f"Bearer {auth_token}"},
        full_name="John Doe",
        id_number="100000009",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["client"]["full_name"] == "John Doe"
    assert data["client"]["id_number"] == "100000009"
    assert data["client"]["id_number_type"] == "corporation"
    assert data["client"]["office_client_number"] == 100001
    assert "id" in data["client"]
    assert "created_at" in data["client"]
    assert data["client"]["created_at"].endswith("Z")


def test_identity_only_client_creation_is_not_available(client, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "full_name": "Identity Only",
            "id_number": "LEGACY-001",
            "id_number_type": "other",
        },
    )

    assert response.status_code == 422


def test_create_client_creates_client_and_initial_business(client, test_db, advisor_headers):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Created Client",
                "id_number": "039337423",
                "entity_type": "company_ltd",
                "phone": "050-1234567",
                "email": "created@example.com",
                "address_street": "Herzl",
                "address_building_number": "12",
                "address_apartment": "3",
                "address_city": "Haifa",
                "address_zip_code": "1234567",
                "vat_reporting_frequency": "monthly",
                "advance_payment_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {
                "business_name": "Created Business",
                "opened_at": "2026-04-19",
            },
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["client"]["full_name"] == "Created Client"
    assert data["business"]["business_name"] == "Created Business"
    assert data["business"]["client_id"] == data["client"]["id"]
    assert data["client"]["office_client_number"] == 100001

    stored_business = test_db.scalars(
        select(Business).filter(
            Business.id == data["business"]["id"],
            Business.business_name == "Created Business",
        )
    ).one()
    assert stored_business.opened_at.isoformat() == "2026-04-19"


def test_create_client_requires_advisor_role(client, secretary_headers):
    response = client.post(
        "/api/v1/clients",
        headers=secretary_headers,
        json={
            "client": {
                "full_name": "Secretary Create",
                "id_number": "039337423",
                "entity_type": "company_ltd",
                "phone": "050-1234567",
                "email": "secretary@example.com",
                "address_street": "Jaffa",
                "address_building_number": "1",
                "address_apartment": "1",
                "address_city": "Tel Aviv",
                "address_zip_code": "1111111",
                "vat_reporting_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {
                "business_name": "Secretary Business",
                "opened_at": "2026-04-19",
            },
        },
    )

    assert response.status_code == 403


def test_create_client_rejects_blank_business_before_creating_client(
    client,
    test_db,
    advisor_headers,
):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Invalid Create",
                "id_number": "039337423",
                "entity_type": "company_ltd",
                "phone": "050-1234567",
                "email": "invalid@example.com",
                "address_street": "Begin",
                "address_building_number": "4",
                "address_apartment": "9",
                "address_city": "Rishon",
                "address_zip_code": "2222222",
                "vat_reporting_frequency": "monthly",
                "advance_payment_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {"business_name": "   ", "opened_at": "2026-04-19"},
        },
    )

    assert response.status_code == 422
    assert (
        test_db.scalar(
            select(func.count())
            .select_from(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .filter(LegalEntity.id_number == "ONB-BLANK")
        )
        == 0
    )


def test_create_client_missing_required_field_returns_friendly_hebrew_message(
    client,
    advisor_headers,
):
    response = client.post(
        "/api/v1/clients",
        headers=advisor_headers,
        json={
            "client": {
                "full_name": "Friendly Error Client",
                "id_number": "039337423",
                "entity_type": "company_ltd",
                "phone": "050-1234567",
                "email": "friendly@example.com",
                "address_street": "",
                "address_building_number": "4",
                "address_apartment": "9",
                "address_city": "Rishon",
                "address_zip_code": "2222222",
                "vat_reporting_frequency": "monthly",
                "advance_payment_frequency": "monthly",
                "accountant_id": 1,
            },
            "business": {
                "business_name": "Friendly Business",
                "opened_at": "2026-04-19",
            },
        },
    )

    assert response.status_code == 422
    errors = response.json()["error"]["details"]
    assert any("יש להזין רחוב" in error["message"] for error in errors)
