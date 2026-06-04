import json
from decimal import Decimal
from itertools import count

import pytest
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
from app.core.exceptions import NotFoundError
from tests.helpers.identity import seed_client_identity

_seq = count(1)


def _create_report(db, user):
    idx = next(_seq)
    client = seed_client_identity(db, full_name=f"Audit Financial {idx}", id_number=f"AF{idx:07d}")
    return AnnualReportService(db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=user.id,
        created_by_name=user.full_name,
    )


def test_income_delete_stores_old_value_snapshot(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_income(
        report.id,
        "salary",
        Decimal("123.45"),
        description="Payroll",
        actor_id=test_user.id,
    )

    service.delete_income(report.id, line.id, actor_id=test_user.id)

    entry = test_db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report.id)
        .filter(EntityAuditLog.action == ACTION_INCOME_DELETED)
    ).one()
    assert json.loads(entry.old_value) == {
        "line_id": line.id,
        "source_type": "salary",
        "amount": "123.45",
        "description": "Payroll",
    }


def test_expense_delete_stores_old_value_snapshot(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_expense(
        report.id,
        "office_rent",
        Decimal("456.78"),
        description="Rent",
        actor_id=test_user.id,
    )

    service.delete_expense(report.id, line.id, actor_id=test_user.id)

    entry = test_db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report.id)
        .filter(EntityAuditLog.action == ACTION_EXPENSE_DELETED)
    ).one()
    assert json.loads(entry.old_value) == {
        "line_id": line.id,
        "category": "office_rent",
        "amount": "456.78",
        "description": "Rent",
    }


def test_cannot_update_income_line_from_another_report(test_db, test_user):
    report_a = _create_report(test_db, test_user)
    report_b = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_income(
        report_a.id,
        "salary",
        Decimal("500.00"),
        actor_id=test_user.id,
    )

    with pytest.raises(NotFoundError):
        service.update_income(
            report_b.id,
            line.id,
            actor_id=test_user.id,
            amount=Decimal("999.00"),
        )

    refreshed = test_db.get(AnnualReportIncomeLine, line.id)
    assert refreshed is not None
    assert refreshed.amount == Decimal("500.00")
    assert (
        test_db.scalars(
            select(EntityAuditLog)
            .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .filter(EntityAuditLog.entity_id == report_b.id)
            .filter(EntityAuditLog.action == ACTION_INCOME_UPDATED)
        ).all()
        == []
    )


def test_cannot_delete_income_line_from_another_report(test_db, test_user):
    report_a = _create_report(test_db, test_user)
    report_b = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_income(
        report_a.id,
        "salary",
        Decimal("500.00"),
        actor_id=test_user.id,
    )

    with pytest.raises(NotFoundError):
        service.delete_income(report_b.id, line.id, actor_id=test_user.id)

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


def test_cannot_update_expense_line_from_another_report(test_db, test_user):
    report_a = _create_report(test_db, test_user)
    report_b = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_expense(
        report_a.id,
        "office_rent",
        Decimal("500.00"),
        actor_id=test_user.id,
    )

    with pytest.raises(NotFoundError):
        service.update_expense(
            report_b.id,
            line.id,
            actor_id=test_user.id,
            amount=Decimal("999.00"),
        )

    refreshed = test_db.get(AnnualReportExpenseLine, line.id)
    assert refreshed is not None
    assert refreshed.amount == Decimal("500.00")
    assert (
        test_db.scalars(
            select(EntityAuditLog)
            .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .filter(EntityAuditLog.entity_id == report_b.id)
            .filter(EntityAuditLog.action == ACTION_EXPENSE_UPDATED)
        ).all()
        == []
    )


def test_cannot_delete_expense_line_from_another_report(test_db, test_user):
    report_a = _create_report(test_db, test_user)
    report_b = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_expense(
        report_a.id,
        "office_rent",
        Decimal("500.00"),
        actor_id=test_user.id,
    )

    with pytest.raises(NotFoundError):
        service.delete_expense(report_b.id, line.id, actor_id=test_user.id)

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
