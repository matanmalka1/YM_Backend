from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from tests.vat.api.test_vat_reports_utils import create_work_item


class TestCreateWorkItem:
    def test_create_work_item_201(self, client, advisor_headers, vat_client):
        item_id = create_work_item(client, advisor_headers, vat_client, "2026-01")
        assert isinstance(item_id, int)

    def test_duplicate_period_400(self, client, advisor_headers, vat_client):
        payload = {"client_record_id": vat_client.id, "period": "2026-02"}
        client.post("/api/v1/vat/work-items", headers=advisor_headers, json=payload)
        response = client.post("/api/v1/vat/work-items", headers=advisor_headers, json=payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "VAT.CONFLICT"

    def test_invalid_period_format_422(self, client, advisor_headers, vat_client):
        response = client.post(
            "/api/v1/vat/work-items",
            headers=advisor_headers,
            json={"client_record_id": vat_client.id, "period": "01-2026"},
        )
        assert response.status_code == 422

    def test_pending_materials_requires_note_400(self, client, advisor_headers, vat_client):
        response = client.post(
            "/api/v1/vat/work-items",
            headers=advisor_headers,
            json={
                "client_record_id": vat_client.id,
                "period": "2026-03",
                "mark_pending": True,
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VAT.PENDING_NOTE_REQUIRED"

    def test_unauthenticated_401(self, client, vat_client):
        response = client.post(
            "/api/v1/vat/work-items",
            json={"client_record_id": vat_client.id, "period": "2026-04"},
        )
        assert response.status_code == 401

    def test_create_work_item_response_is_enriched(
        self, client, test_db, advisor_headers, vat_client
    ):
        assignee = User(
            full_name="VAT Assignee",
            email="vat.assignee.intake@example.com",
            password_hash=AuthService.hash_password("pass"),
            role=UserRole.SECRETARY,
            is_active=True,
        )
        test_db.add(assignee)
        test_db.commit()
        test_db.refresh(assignee)

        response = client.post(
            "/api/v1/vat/work-items",
            headers=advisor_headers,
            json={
                "client_record_id": vat_client.id,
                "period": "2026-05",
                "assigned_to": assignee.id,
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["client_name"] == vat_client.full_name
        assert body["client_record_id"] == vat_client.id
        assert body["assigned_to_name"] == "VAT Assignee"
        assert body["submission_deadline"] == "2026-06-15"
        assert [action["key"] for action in body["available_actions"]] == ["add_invoice"]
