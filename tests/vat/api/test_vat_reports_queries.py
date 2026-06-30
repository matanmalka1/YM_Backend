from datetime import date

from sqlalchemy import select

from app.businesses.models.business import BusinessStatus
from app.common.enums import IdNumberType, VatType
from app.users.models.user import User, UserRole
from app.utils.time_utils import utcnow
from app.vat.models.vat_work_item import VatWorkItem
from tests.factories import create_user
from tests.helpers.identity import seed_business, seed_client_identity
from tests.vat.api.test_vat_reports_utils import (
    create_work_item,
    income_payload,
)


def _create_user(test_db, email: str, full_name: str, role: UserRole) -> User:
    user = create_user(
        test_db,
        full_name=full_name,
        email=email,
        password="pass",
        role=role,
        is_active=True,
        commit=True,
    )
    return user


def _create_vat_client_with_name(test_db, full_name: str, id_number: str):
    client = seed_client_identity(
        test_db,
        full_name=full_name,
        id_number=id_number,
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name=full_name,
        status=BusinessStatus.ACTIVE,
        opened_at=date.today(),
    )
    test_db.commit()
    return client


def test_get_work_item_includes_user_names_and_deadline_fields(
    client, test_db, advisor_headers, vat_client, test_user
):
    assignee = _create_user(
        test_db,
        email="vat.assignee@example.com",
        full_name="VAT Assignee",
        role=UserRole.SECRETARY,
    )

    create_resp = client.post(
        "/api/v1/vat/work-items",
        headers=advisor_headers,
        json={
            "client_record_id": vat_client.id,
            "period": "2026-08",
            "assigned_to": assignee.id,
        },
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]

    add_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-QRY-1"),
    )
    assert add_resp.status_code == 201

    ready_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/ready-for-review",
        headers=advisor_headers,
    )
    assert ready_resp.status_code == 200

    file_resp = client.post(
        f"/api/v1/vat/work-items/{item_id}/file",
        headers=advisor_headers,
        json={"submission_method": "online"},
    )
    assert file_resp.status_code == 200

    get_resp = client.get(f"/api/v1/vat/work-items/{item_id}", headers=advisor_headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == item_id
    assert body["assigned_to_name"] == "VAT Assignee"
    assert body["filed_by_name"] == test_user.full_name
    assert body["submission_deadline"] == "2026-09-24"
    assert isinstance(body["days_until_deadline"], int)
    assert isinstance(body["is_overdue"], bool)


def test_list_work_items_supports_status_and_client_name_filters(
    client, advisor_headers, vat_client, test_user
):
    filed_item_id = create_work_item(
        client, advisor_headers, vat_client, "2026-09", assigned_to=test_user.id
    )
    pending_item_id = create_work_item(client, advisor_headers, vat_client, "2026-10")

    add_resp = client.post(
        f"/api/v1/vat/work-items/{filed_item_id}/invoices",
        headers=advisor_headers,
        json=income_payload(invoice_number="INV-QRY-2"),
    )
    assert add_resp.status_code == 201
    assert (
        client.post(
            f"/api/v1/vat/work-items/{filed_item_id}/ready-for-review",
            headers=advisor_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/vat/work-items/{filed_item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        ).status_code
        == 200
    )

    list_resp = client.get(
        f"/api/v1/vat/work-items?status=filed&client_name={vat_client.full_name}",
        headers=advisor_headers,
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == filed_item_id
    assert body["items"][0]["status"] == "filed"
    assert body["items"][0]["client_name"] == vat_client.full_name
    assert body["items"][0]["id"] != pending_item_id


def test_status_summary_returns_all_statuses_and_counts_by_filter(
    client, test_db, advisor_headers, vat_client, test_user
):
    same_name_client = _create_vat_client_with_name(
        test_db,
        vat_client.full_name,
        "987654321",
    )
    other_pending_resp = client.post(
        "/api/v1/vat/work-items",
        headers=advisor_headers,
        json={
            "client_record_id": same_name_client.id,
            "period": "2026-01",
            "mark_pending": True,
            "pending_materials_note": "same name, different record",
        },
    )
    assert other_pending_resp.status_code == 201

    pending_resp = client.post(
        "/api/v1/vat/work-items",
        headers=advisor_headers,
        json={
            "client_record_id": vat_client.id,
            "period": "2026-01",
            "mark_pending": True,
            "pending_materials_note": "חסרים מסמכים",
        },
    )
    assert pending_resp.status_code == 201
    create_work_item(client, advisor_headers, vat_client, "2026-02")
    data_entry_item_id = create_work_item(client, advisor_headers, vat_client, "2026-03")
    ready_item_id = create_work_item(client, advisor_headers, vat_client, "2026-04")
    filed_item_id = create_work_item(
        client, advisor_headers, vat_client, "2026-05", assigned_to=test_user.id
    )
    deleted_item_id = create_work_item(client, advisor_headers, vat_client, "2026-06")
    _ = create_work_item(client, advisor_headers, vat_client, "2027-01")

    for item_id in [data_entry_item_id, ready_item_id, filed_item_id]:
        add_resp = client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json=income_payload(invoice_number=f"INV-SUM-{item_id}"),
        )
        assert add_resp.status_code == 201

    ready_resp = client.post(
        f"/api/v1/vat/work-items/{ready_item_id}/ready-for-review",
        headers=advisor_headers,
    )
    assert ready_resp.status_code == 200
    filed_ready_resp = client.post(
        f"/api/v1/vat/work-items/{filed_item_id}/ready-for-review",
        headers=advisor_headers,
    )
    assert filed_ready_resp.status_code == 200
    file_resp = client.post(
        f"/api/v1/vat/work-items/{filed_item_id}/file",
        headers=advisor_headers,
        json={"submission_method": "online"},
    )
    assert file_resp.status_code == 200

    deleted_item = test_db.get(VatWorkItem, deleted_item_id)
    deleted_item.deleted_at = utcnow()
    test_db.commit()

    response = client.get(
        f"/api/v1/vat/work-items/status-summary?year=2026&client_name={vat_client.full_name}",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "pending_materials": 2,
        "material_received": 1,
        "data_entry_in_progress": 1,
        "ready_for_review": 1,
        "filed": 1,
        "canceled": 0,
    }

    exact_response = client.get(
        f"/api/v1/vat/work-items/status-summary?year=2026&client_record_id={vat_client.id}",
        headers=advisor_headers,
    )

    assert exact_response.status_code == 200
    assert exact_response.json() == {
        "pending_materials": 1,
        "material_received": 1,
        "data_entry_in_progress": 1,
        "ready_for_review": 1,
        "filed": 1,
        "canceled": 0,
    }


def test_grouped_work_items_filter_by_exact_client_record_id(
    client, test_db, advisor_headers, vat_client
):
    same_name_client = _create_vat_client_with_name(
        test_db,
        vat_client.full_name,
        "987654322",
    )
    create_work_item(client, advisor_headers, vat_client, "2026-01")
    create_work_item(client, advisor_headers, same_name_client, "2026-02")

    groups_resp = client.get(
        f"/api/v1/vat/work-items/groups?year=2026&client_record_id={vat_client.id}",
        headers=advisor_headers,
    )

    assert groups_resp.status_code == 200
    groups = groups_resp.json()["groups"]
    assert sum(group["total_count"] for group in groups) == 1


def test_list_work_items_supports_filter_by_client_name_and_id_number(
    client, advisor_headers, vat_client
):
    target_item_id = create_work_item(client, advisor_headers, vat_client, "2026-11")
    _ = create_work_item(client, advisor_headers, vat_client, "2026-12")

    by_client_id = client.get(
        f"/api/v1/vat/work-items?client_name={vat_client.id_number}",
        headers=advisor_headers,
    )
    assert by_client_id.status_code == 200
    payload_client_id = by_client_id.json()
    assert payload_client_id["total"] >= 1
    assert any(item["id"] == target_item_id for item in payload_client_id["items"])

    by_name = client.get(
        f"/api/v1/vat/work-items?client_name={vat_client.full_name}",
        headers=advisor_headers,
    )
    assert by_name.status_code == 200
    payload_name = by_name.json()
    assert payload_name["total"] >= 1
    assert any(item["id"] == target_item_id for item in payload_name["items"])


def test_list_client_work_items_supports_pagination(client, advisor_headers, vat_client):
    created_ids = [
        create_work_item(client, advisor_headers, vat_client, f"2026-{month:02d}")
        for month in range(1, 4)
    ]

    resp = client.get(
        f"/api/v1/vat/clients/{vat_client.id}/work-items?page=1&page_size=2",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert [item["id"] for item in body["items"]] == [created_ids[2], created_ids[1]]


def test_lookup_work_item_normalizes_bimonthly_period(client, advisor_headers, vat_client):
    item_id = create_work_item(client, advisor_headers, vat_client, "2026-03")

    resp = client.get(
        f"/api/v1/vat/work-items/lookup?client_record_id={vat_client.id}&period=2026-03-04",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["id"] == item_id


def test_period_options_default_monthly_returns_12_periods(client, advisor_headers, vat_client):
    resp = client.get(
        f"/api/v1/vat/clients/{vat_client.id}/period-options?year=2026",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["period_type"] == "monthly"
    assert len(body["options"]) == 12
    assert body["options"][0]["period"] == "2026-01"
    assert body["options"][0]["label"] == "2026-01"
    assert body["options"][1]["period"] == "2026-02"
    assert body["options"][11]["period"] == "2026-12"
    assert all(not option["is_opened"] for option in body["options"])


def test_period_options_bimonthly_uses_odd_months_and_marks_opened(
    client, advisor_headers, vat_client, test_db
):
    from app.legal_entities.models.legal_entity import LegalEntity

    le = test_db.scalars(
        select(LegalEntity).filter(LegalEntity.id == vat_client.legal_entity_id)
    ).first()
    le.vat_reporting_frequency = VatType.BIMONTHLY
    test_db.commit()

    create_resp = client.post(
        "/api/v1/vat/work-items",
        headers=advisor_headers,
        json={"client_record_id": vat_client.id, "period": "2026-03"},
    )
    assert create_resp.status_code == 201

    resp = client.get(
        f"/api/v1/vat/clients/{vat_client.id}/period-options?year=2026",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["period_type"] == "bimonthly"
    periods = [option["period"] for option in body["options"]]
    assert periods == ["2026-01", "2026-03", "2026-05", "2026-07", "2026-09", "2026-11"]
    labels = [option["label"] for option in body["options"]]
    assert labels[0] == "2026-01/2026-02"
    assert labels[1] == "2026-03/2026-04"
    opened = {option["period"]: option["is_opened"] for option in body["options"]}
    assert opened["2026-03"] is True
    assert opened["2026-01"] is False
