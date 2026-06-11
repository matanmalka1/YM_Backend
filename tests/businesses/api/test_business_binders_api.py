from datetime import date

from app.binders.models.binder import Binder
from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.common.enums import IdNumberType
from app.legal_entities.models.legal_entity import LegalEntity


def _seed_client_business_and_binder(test_db, *, user_id: int):
    legal_entity = LegalEntity(
        official_name="Binders Client",
        id_number="720000001",
        id_number_type=IdNumberType.CORPORATION,
    )
    test_db.add(legal_entity)
    test_db.commit()
    test_db.refresh(legal_entity)

    client_record = ClientRecord(legal_entity_id=legal_entity.id, created_by=user_id)
    test_db.add(client_record)
    test_db.commit()
    test_db.refresh(client_record)

    business = Business(
        legal_entity_id=legal_entity.id,
        business_name="Binders Biz",
        opened_at=date(2025, 1, 1),
        created_by=user_id,
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)

    binder = Binder(
        client_record_id=client_record.id,
        binder_number="BIZ-BIND-001",
        period_start=date(2026, 1, 1),
        created_by=user_id,
    )
    test_db.add(binder)
    test_db.commit()
    test_db.refresh(binder)

    return business, binder, client_record.id


def test_list_business_binders_returns_client_binders(client, test_db, test_user, advisor_headers):
    business, binder, client_record_id = _seed_client_business_and_binder(
        test_db, user_id=test_user.id
    )

    response = client.get(
        f"/api/v1/clients/{client_record_id}/binders?page=1&page_size=20",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == binder.id
    assert data["items"][0]["client_record_id"] == client_record_id
    assert data["items"][0]["binder_number"] == "BIZ-BIND-001"


def test_list_business_binders_business_not_found(client, advisor_headers):
    response = client.get(
        "/api/v1/clients/999999/binders?page=1&page_size=20",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLIENT.NOT_FOUND"
