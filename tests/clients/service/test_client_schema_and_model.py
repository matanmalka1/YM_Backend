import pytest
from pydantic import ValidationError

from app.clients.schemas.client import ClientOnboardingRequest


def _payload(**client_overrides):
    client_payload = {
        "full_name": "Bad",
        "id_number": "123456789",
        "entity_type": "osek_murshe",
        "phone": "050-1234567",
        "email": "bad@example.com",
        "address_street": "Main",
        "address_building_number": "1",
        "address_apartment": "1",
        "address_city": "Tel Aviv",
        "address_zip_code": "1234567",
        "accountant_id": 1,
        "vat_reporting_frequency": "monthly",
        "advance_payment_frequency": "monthly",
    }
    client_payload.update(client_overrides)
    return {
        "client": client_payload,
        "business": {"business_name": "Biz", "opened_at": None},
    }


def test_create_request_rejects_non_digits_for_osek():
    with pytest.raises(ValidationError):
        ClientOnboardingRequest.model_validate(_payload(id_number="12A456789"))


def test_create_request_rejects_invalid_length_for_osek():
    with pytest.raises(ValidationError):
        ClientOnboardingRequest.model_validate(_payload(id_number="12345"))


def test_create_request_accepts_valid_individual_checksum():
    request = ClientOnboardingRequest.model_validate(_payload(id_number="100000009"))

    assert request.client.id_number == "100000009"


def test_create_request_rejects_invalid_individual_checksum():
    with pytest.raises(ValidationError, match="מספר תעודת זהות אינו תקין"):
        ClientOnboardingRequest.model_validate(_payload(id_number="100000008"))


def test_create_request_rejects_manual_vat_frequency_for_osek_patur():
    with pytest.raises(ValidationError):
        ClientOnboardingRequest.model_validate(
            _payload(entity_type="osek_patur", vat_reporting_frequency="exempt"),
        )


def test_create_request_rejects_conflicting_company_identifier_type():
    with pytest.raises(ValidationError):
        ClientOnboardingRequest.model_validate(
            _payload(
                entity_type="company_ltd",
                id_number="039337423",
                id_number_type="individual",
            ),
        )
