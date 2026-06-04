from itertools import count

from sqlalchemy import select

from app.annual_reports.models.annual_report_expense_line import AnnualReportExpenseLine
from app.annual_reports.models.annual_report_income_line import AnnualReportIncomeLine
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.financial_service import AnnualReportFinancialService
from app.audit.constants import (
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.models.entity_audit_log import EntityAuditLog
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
    line = AnnualReportFinancialService(test_db).add_income(report_a.id, "salary", 500)

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
    line = AnnualReportFinancialService(test_db).add_income(report_a.id, "salary", 500)

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
    line = AnnualReportFinancialService(test_db).add_expense(
        report_a.id, "office_rent", 500
    )

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
    line = AnnualReportFinancialService(test_db).add_expense(
        report_a.id, "office_rent", 500
    )

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
