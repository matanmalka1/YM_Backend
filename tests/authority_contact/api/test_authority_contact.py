from app.authority_contact.models.authority_contact import ContactType
from app.authority_contact.repositories.authority_contact_repository import (
    AuthorityContactRepository,
)
from tests.helpers.identity import seed_client_identity


def _create_client(test_db, id_number: str = "777777777"):
    client = seed_client_identity(
        test_db,
        full_name="Authority Contact Client",
        id_number=id_number,
    )
    test_db.commit()
    return client


def _create_contact(test_db, client_id: int, contact_type: ContactType = ContactType.VAT_BRANCH):
    return AuthorityContactRepository(test_db).create(
        client_record_id=client_id,
        contact_type=contact_type,
        name="Branch Contact",
        office="Tel Aviv",
        phone="03-1234567",
        email="branch@example.com",
    )


# ── create ───────────────────────────────────────────────────────────────────


def test_create_authority_contact(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)

    response = client.post(
        f"/api/v1/clients/{crm_client.id}/authority-contacts",
        headers=advisor_headers,
        json={
            "contact_type": "vat_branch",
            "name": "Ms. VAT",
            "office": "Central",
            "phone": "03-0000000",
            "email": "vat@example.com",
            "notes": "Handles VAT filings",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["contact_type"] == "vat_branch"
    assert data["name"] == "Ms. VAT"
    assert data["created_at"] is not None

    stored = AuthorityContactRepository(test_db).get_by_id(data["id"])
    assert stored is not None
    assert stored.contact_type == ContactType.VAT_BRANCH


def test_create_authority_contact_unknown_client_returns_404(client, advisor_headers):
    response = client.post(
        "/api/v1/clients/999/authority-contacts",
        headers=advisor_headers,
        json={"contact_type": "vat_branch", "name": "Ghost"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLIENT.NOT_FOUND"


def test_create_authority_contact_invalid_contact_type_returns_422(
    client, test_db, advisor_headers
):
    crm_client = _create_client(test_db)

    response = client.post(
        f"/api/v1/clients/{crm_client.id}/authority-contacts",
        headers=advisor_headers,
        json={"contact_type": "invalid_type", "name": "Bad Type"},
    )

    assert response.status_code == 422


# ── list ─────────────────────────────────────────────────────────────────────


def test_list_authority_contacts_filters_by_type(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)
    _create_contact(test_db, crm_client.id, ContactType.VAT_BRANCH)
    _create_contact(test_db, crm_client.id, ContactType.ASSESSING_OFFICER)
    _create_contact(test_db, crm_client.id, ContactType.VAT_BRANCH)

    response = client.get(
        f"/api/v1/clients/{crm_client.id}/authority-contacts?contact_type=vat_branch&page=1&page_size=10",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert all(item["contact_type"] == "vat_branch" for item in data["items"])


def test_list_authority_contacts_invalid_contact_type_returns_422(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)

    response = client.get(
        f"/api/v1/clients/{crm_client.id}/authority-contacts?contact_type=invalid_type",
        headers=advisor_headers,
    )

    assert response.status_code == 422


# ── get ──────────────────────────────────────────────────────────────────────


def test_get_authority_contact(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)
    contact = _create_contact(test_db, crm_client.id)

    response = client.get(
        f"/api/v1/clients/{crm_client.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == contact.id


def test_get_authority_contact_not_found(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)

    response = client.get(
        f"/api/v1/clients/{crm_client.id}/authority-contacts/999999",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUTHORITY_CONTACT.NOT_FOUND"


def test_get_authority_contact_wrong_client_returns_404(client, test_db, advisor_headers):
    owner = _create_client(test_db, id_number="111111111")
    other = _create_client(test_db, id_number="222222222")
    contact = _create_contact(test_db, owner.id)

    response = client.get(
        f"/api/v1/clients/{other.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUTHORITY_CONTACT.NOT_FOUND"


# ── update ───────────────────────────────────────────────────────────────────


def test_update_authority_contact(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)
    contact = _create_contact(test_db, crm_client.id, ContactType.VAT_BRANCH)

    response = client.patch(
        f"/api/v1/clients/{crm_client.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
        json={"name": "Updated Name", "contact_type": "assessing_officer"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["contact_type"] == "assessing_officer"
    assert data["updated_at"] is not None


def test_update_authority_contact_wrong_client_returns_404(client, test_db, advisor_headers):
    owner = _create_client(test_db, id_number="333333333")
    other = _create_client(test_db, id_number="444444444")
    contact = _create_contact(test_db, owner.id)

    response = client.patch(
        f"/api/v1/clients/{other.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
        json={"name": "Stolen Name"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUTHORITY_CONTACT.NOT_FOUND"


def test_update_authority_contact_invalid_contact_type_returns_422(
    client, test_db, advisor_headers
):
    crm_client = _create_client(test_db)
    contact = _create_contact(test_db, crm_client.id, ContactType.VAT_BRANCH)

    response = client.patch(
        f"/api/v1/clients/{crm_client.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
        json={"contact_type": "invalid_type"},
    )

    assert response.status_code == 422


# ── delete ───────────────────────────────────────────────────────────────────


def test_delete_authority_contact_soft_deletes(client, test_db, advisor_headers):
    crm_client = _create_client(test_db)
    contact = _create_contact(test_db, crm_client.id)

    response = client.delete(
        f"/api/v1/clients/{crm_client.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 204

    repo = AuthorityContactRepository(test_db)
    assert repo.get_by_id(contact.id) is None
    list_response = client.get(
        f"/api/v1/clients/{crm_client.id}/authority-contacts",
        headers=advisor_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_delete_authority_contact_wrong_client_returns_404(client, test_db, advisor_headers):
    owner = _create_client(test_db, id_number="555555555")
    other = _create_client(test_db, id_number="666666666")
    contact = _create_contact(test_db, owner.id)

    response = client.delete(
        f"/api/v1/clients/{other.id}/authority-contacts/{contact.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUTHORITY_CONTACT.NOT_FOUND"

    # Original contact untouched
    assert AuthorityContactRepository(test_db).get_by_id(contact.id) is not None


def test_secretary_cannot_delete_authority_contact(client, test_db, secretary_headers):
    crm_client = _create_client(test_db)
    contact = _create_contact(test_db, crm_client.id)

    response = client.delete(
        f"/api/v1/clients/{crm_client.id}/authority-contacts/{contact.id}",
        headers=secretary_headers,
    )

    assert response.status_code == 403
