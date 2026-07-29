from tests.vat.api.test_vat_reports_utils import setup_ready_item


class TestFiling:
    def test_file_vat_return(self, client, advisor_headers, vat_client, test_user):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2026-12", assigned_to=test_user.id
        )
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["submission_method"] == "online"
        assert data["is_overridden"] is False

    def test_file_vat_return_records_filed_audit(
        self, client, advisor_headers, vat_client, test_user
    ):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2026-11", assigned_to=test_user.id
        )
        file_response = client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        )
        assert file_response.status_code == 200

        # Reads now go through the generic audit endpoint (vat_work_item entity).
        audit_response = client.get(
            f"/api/v1/audit/vat_work_item/{item_id}",
            headers=advisor_headers,
        )
        assert audit_response.status_code == 200
        filed_entries = [
            entry
            for entry in audit_response.json()["items"]
            if entry["action"] == "vat_work_item.filed"
        ]
        assert len(filed_entries) == 1
        assert filed_entries[0]["new_value"]["submission_method"] == "online"

    def test_cannot_file_without_advisor_role(self, client, secretary_headers, vat_client):
        response = client.post(
            "/api/v1/vat/work-items/1/file",
            headers=secretary_headers,
            json={"submission_method": "online"},
        )
        assert response.status_code == 403

    def test_cannot_add_invoice_after_filing(self, client, advisor_headers, vat_client, test_user):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2025-01", assigned_to=test_user.id
        )
        client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "manual"},
        )
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/invoices",
            headers=advisor_headers,
            json={
                "invoice_type": "income",
                "invoice_number": "INV-999",
                "invoice_date": "2026-01-20T00:00:00",
                "counterparty_name": "Late customer",
                "gross_amount": "590.00",
            },
        )
        assert response.status_code == 400

    def test_override_with_justification_works(
        self, client, advisor_headers, vat_client, test_user
    ):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2025-02", assigned_to=test_user.id
        )
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={
                "submission_method": "manual",
                "override_amount": "200.00",
                "override_justification": "Corrected invoice received post-review",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_overridden"] is True
        assert data["final_vat_amount"] == "200.00"

    def test_override_without_justification_400(
        self, client, advisor_headers, vat_client, test_user
    ):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2025-03", assigned_to=test_user.id
        )
        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online", "override_amount": "999.00"},
        )
        assert response.status_code == 400

    def test_filing_with_submission_reference(self, client, advisor_headers, vat_client, test_user):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2025-04", assigned_to=test_user.id
        )

        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={
                "submission_method": "online",
                "submission_reference": "REF-2025-0001",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["submission_reference"] == "REF-2025-0001"
        # Filing never marks a row as an amendment: a correction is a separate
        # record created by POST /amend (D-10), not a flag set at filing time.
        assert data["amends_id"] is None
        assert data["superseded_at"] is None

    def test_file_response_is_enriched(self, client, advisor_headers, vat_client, test_user):
        item_id = setup_ready_item(
            client, advisor_headers, vat_client, "2026-08", assigned_to=test_user.id
        )

        response = client.post(
            f"/api/v1/vat/work-items/{item_id}/file",
            headers=advisor_headers,
            json={"submission_method": "online"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["client_name"] == vat_client.full_name
        assert data["client_record_id"] == vat_client.id
        assert data["closed_by_name"] == test_user.full_name
        assert data["submission_deadline"] == "2026-09-24"
