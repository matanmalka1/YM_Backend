from itertools import count

from sqlalchemy import select

from app.annual_reports.api import annual_report_financials as financials_api
from app.annual_reports.models.annual_report_expense_line import AnnualReportExpenseLine
from app.annual_reports.models.annual_report_income_line import AnnualReportIncomeLine
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.financial_line_service import AnnualReportFinancialLineService
from app.audit.constants import (
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.models.entity_audit_log import EntityAuditLog
from app.clients.enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from tests.helpers.identity import seed_client_identity

_client_seq = count(1)


def _create_report(db):
    client = seed_client_identity(
        db, full_name="Financial Client", id_number=f"56565656{next(_client_seq)}"
    )

    svc = AnnualReportService(db)
    return svc.create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
        created_by_name="Tester",
        deadline_type="standard",
        notes=None,
    )


def test_create_income_line_accepts_zero_amount(client, test_db, advisor_headers):
    report = _create_report(test_db)

    resp = client.post(
        f"/api/v1/annual-reports/{report.id}/income",
        headers=advisor_headers,
        json={"source_type": "salary", "amount": 0, "description": "Zeroed correction"},
    )

    assert resp.status_code == 201
    assert resp.json()["amount"] == "0.00"


def test_cannot_update_income_line_from_another_report_api(client, test_db, advisor_headers):
    report_a = _create_report(test_db)
    report_b = _create_report(test_db)
    line = AnnualReportFinancialLineService(test_db).add_income(report_a.id, "salary", 500)

    response = client.patch(
        f"/api/v1/annual-reports/{report_b.id}/income/{line.id}",
        headers=advisor_headers,
        json={"amount": 999},
    )

    assert response.status_code == 404
    refreshed = test_db.get(AnnualReportIncomeLine, line.id)
    assert refreshed is not None
    assert refreshed.amount == 500
    assert (
        test_db.scalars(
            select(EntityAuditLog)
            .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .filter(EntityAuditLog.entity_id == report_b.id)
            .filter(EntityAuditLog.action == ACTION_INCOME_UPDATED)
        ).all()
        == []
    )


def test_cannot_delete_income_line_from_another_report_api(client, test_db, advisor_headers):
    report_a = _create_report(test_db)
    report_b = _create_report(test_db)
    line = AnnualReportFinancialLineService(test_db).add_income(report_a.id, "salary", 500)

    response = client.delete(
        f"/api/v1/annual-reports/{report_b.id}/income/{line.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert test_db.get(AnnualReportIncomeLine, line.id) is not None
    assert (
        test_db.scalars(
            select(EntityAuditLog)
            .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .filter(EntityAuditLog.entity_id == report_b.id)
            .filter(EntityAuditLog.action == ACTION_INCOME_DELETED)
        ).all()
        == []
    )


def test_cannot_update_expense_line_from_another_report_api(client, test_db, advisor_headers):
    report_a = _create_report(test_db)
    report_b = _create_report(test_db)
    line = AnnualReportFinancialLineService(test_db).add_expense(report_a.id, "office_rent", 500)

    response = client.patch(
        f"/api/v1/annual-reports/{report_b.id}/expenses/{line.id}",
        headers=advisor_headers,
        json={"amount": 999},
    )

    assert response.status_code == 404
    refreshed = test_db.get(AnnualReportExpenseLine, line.id)
    assert refreshed is not None
    assert refreshed.amount == 500
    assert (
        test_db.scalars(
            select(EntityAuditLog)
            .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .filter(EntityAuditLog.entity_id == report_b.id)
            .filter(EntityAuditLog.action == ACTION_EXPENSE_UPDATED)
        ).all()
        == []
    )


def test_cannot_delete_expense_line_from_another_report_api(client, test_db, advisor_headers):
    report_a = _create_report(test_db)
    report_b = _create_report(test_db)
    line = AnnualReportFinancialLineService(test_db).add_expense(report_a.id, "office_rent", 500)

    response = client.delete(
        f"/api/v1/annual-reports/{report_b.id}/expenses/{line.id}",
        headers=advisor_headers,
    )

    assert response.status_code == 404
    assert test_db.get(AnnualReportExpenseLine, line.id) is not None
    assert (
        test_db.scalars(
            select(EntityAuditLog)
            .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .filter(EntityAuditLog.entity_id == report_b.id)
            .filter(EntityAuditLog.action == ACTION_EXPENSE_DELETED)
        ).all()
        == []
    )


def test_update_income_line_blocks_frozen_client_api(client, test_db, advisor_headers):
    report = _create_report(test_db)
    line = AnnualReportFinancialLineService(test_db).add_income(report.id, "salary", 500)
    client_record = test_db.get(ClientRecord, report.client_record_id)
    client_record.status = ClientStatus.FROZEN
    test_db.flush()

    response = client.patch(
        f"/api/v1/annual-reports/{report.id}/income/{line.id}",
        headers=advisor_headers,
        json={"amount": 999},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CLIENT.FROZEN"
    refreshed = test_db.get(AnnualReportIncomeLine, line.id)
    assert refreshed.amount == 500


def test_auto_populate_response_contract_includes_skips_and_breakdown(
    client, advisor_headers, monkeypatch
):
    calls = []

    class _FakeVatImportService:
        def __init__(self, db):
            pass

        def auto_populate(self, report_id, force=False, actor_id=None):
            calls.append({"report_id": report_id, "force": force, "actor_id": actor_id})
            return {
                "annual_report_id": report_id,
                "income_lines_created": 0,
                "expense_lines_created": 1,
                "income_total": "0.00",
                "expense_total": "1200.00",
                "lines_deleted": 0,
                "skipped_items": [
                    {
                        "item_type": "income",
                        "source": "business",
                        "amount": "-50.00",
                        "reason": "negative_total",
                        "annual_category": None,
                    }
                ],
                "warnings": ["VAT import skipped negative business income total."],
                "expense_breakdown": [
                    {
                        "annual_category": "vehicle",
                        "amount": "1200.00",
                        "source_vat_categories": {
                            "fuel": "800.00",
                            "vehicle_maintenance": "400.00",
                        },
                    }
                ],
            }

    monkeypatch.setattr(financials_api, "VatImportService", _FakeVatImportService)

    response = client.post(
        "/api/v1/annual-reports/123/auto-populate?force=true",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["report_id"] == 123
    assert calls[0]["force"] is True
    assert isinstance(calls[0]["actor_id"], int)
    payload = response.json()
    assert payload["skipped_items"] == [
        {
            "item_type": "income",
            "source": "business",
            "amount": "-50.00",
            "reason": "negative_total",
            "annual_category": None,
        }
    ]
    assert payload["expense_breakdown"][0]["source_vat_categories"] == {
        "fuel": "800.00",
        "vehicle_maintenance": "400.00",
    }


def test_auto_populate_blocks_frozen_client_api(client, test_db, advisor_headers):
    report = _create_report(test_db)
    AnnualReportFinancialLineService(test_db).add_income(report.id, "salary", 500)
    client_record = test_db.get(ClientRecord, report.client_record_id)
    client_record.status = ClientStatus.FROZEN
    test_db.flush()

    response = client.post(
        f"/api/v1/annual-reports/{report.id}/auto-populate?force=true",
        headers=advisor_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CLIENT.FROZEN"
