def make_client_create_payload(
    *,
    full_name="Test Client",
    id_number="039337423",
    business_name="Test Business",
    opened_at=None,
    accountant_id=None,
    **client_overrides,
):
    # accountant_id is a nullable FK to users; it must stay None unless the caller passes a
    # real user id, otherwise the insert fails against a database with no seeded users.
    client_payload = {
        "full_name": full_name,
        "id_number": id_number,
        "entity_type": "company_ltd",
        "phone": "050-1234567",
        "email": "test@example.com",
        "address_street": "Main",
        "address_building_number": "10",
        "address_apartment": "5",
        "address_city": "Tel Aviv",
        "address_zip_code": "1234567",
        "vat_reporting_frequency": "monthly",
        "advance_payment_frequency": "monthly",
        "accountant_id": accountant_id,
    }
    client_payload.update(client_overrides)
    return {
        "client": client_payload,
        "business": {
            "business_name": business_name,
            "opened_at": opened_at,
        },
    }


def create_client_via_api(client, headers, **payload_overrides):
    return client.post(
        "/api/v1/clients",
        headers=headers,
        json=make_client_create_payload(**payload_overrides),
    )
