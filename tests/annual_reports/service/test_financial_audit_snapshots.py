import json
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.annual_reports.models.annual_report_expense_line import (
    AnnualReportExpenseLine,
    ExpenseCategoryType,
)
from app.annual_reports.models.annual_report_income_line import (
    AnnualReportIncomeLine,
    IncomeSourceType,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.financial_service import AnnualReportFinancialService
from app.annual_reports.services.financial_line_helpers import audit_scalar
from app.audit.constants import (
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_ADDED,
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


def _audit_entries(db, report_id: int, action: str) -> list[EntityAuditLog]:
    return db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report_id)
        .filter(EntityAuditLog.action == action)
    ).all()


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
        "recognition_rate": "1.00",
        "external_document_reference": None,
        "supporting_document_id": None,
        "description": "Rent",
    }


def test_income_add_stores_snapshot_payload(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_income(
        report.id,
        "salary",
        Decimal("123.45"),
        description="Payroll",
        actor_id=test_user.id,
    )

    entry = _audit_entries(test_db, report.id, ACTION_INCOME_ADDED)[0]

    assert json.loads(entry.new_value) == {
        "line_id": line.id,
        "source_type": "salary",
        "amount": "123.45",
        "description": "Payroll",
    }


def test_expense_add_stores_full_snapshot_payload(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_expense(
        report.id,
        "office_rent",
        Decimal("456.78"),
        description="Rent",
        recognition_rate=Decimal("0.75"),
        external_document_reference="INV-100",
        actor_id=test_user.id,
    )

    entry = _audit_entries(test_db, report.id, ACTION_EXPENSE_ADDED)[0]

    assert json.loads(entry.new_value) == {
        "line_id": line.id,
        "category": "office_rent",
        "amount": "456.78",
        "recognition_rate": "0.75",
        "external_document_reference": "INV-100",
        "supporting_document_id": None,
        "description": "Rent",
    }


def test_income_update_audit_excludes_none_fields(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_income(
        report.id,
        "salary",
        Decimal("500.00"),
        description="Payroll",
        actor_id=test_user.id,
    )

    service.update_income(
        report.id,
        line.id,
        actor_id=test_user.id,
        amount=Decimal("600.00"),
        description=None,
    )

    entry = _audit_entries(test_db, report.id, ACTION_INCOME_UPDATED)[0]
    assert json.loads(entry.new_value) == {"amount": "600.00"}


def test_expense_update_audit_stores_full_old_snapshot_and_excludes_none_fields(
    test_db, test_user
):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    line = service.add_expense(
        report.id,
        "office_rent",
        Decimal("500.00"),
        description="Rent",
        recognition_rate=Decimal("0.50"),
        external_document_reference="INV-OLD",
        actor_id=test_user.id,
    )

    service.update_expense(
        report.id,
        line.id,
        actor_id=test_user.id,
        recognition_rate=Decimal("0.75"),
        description=None,
    )

    entry = _audit_entries(test_db, report.id, ACTION_EXPENSE_UPDATED)[0]
    assert json.loads(entry.old_value) == {
        "line_id": line.id,
        "category": "office_rent",
        "amount": "500.00",
        "recognition_rate": "0.50",
        "external_document_reference": "INV-OLD",
        "supporting_document_id": None,
        "description": "Rent",
    }
    assert json.loads(entry.new_value) == {"recognition_rate": "0.75"}


def test_empty_financial_line_updates_do_not_write_audit(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    income = service.add_income(report.id, "salary", Decimal("500.00"), actor_id=test_user.id)
    expense = service.add_expense(
        report.id,
        "office_rent",
        Decimal("500.00"),
        actor_id=test_user.id,
    )

    service.update_income(report.id, income.id, actor_id=test_user.id, description=None)
    service.update_expense(report.id, expense.id, actor_id=test_user.id, description=None)

    assert _audit_entries(test_db, report.id, ACTION_INCOME_UPDATED) == []
    assert _audit_entries(test_db, report.id, ACTION_EXPENSE_UPDATED) == []


def test_financial_line_repositories_reject_unsupported_update_fields(test_db, test_user):
    report = _create_report(test_db, test_user)
    service = AnnualReportFinancialService(test_db)
    income = service.income_repo.create_for_report(
        report.id,
        IncomeSourceType.SALARY,
        Decimal("500.00"),
    )
    expense = service.expense_repo.create_for_report(
        report.id,
        ExpenseCategoryType.OFFICE_RENT,
        Decimal("500.00"),
        Decimal("1.00"),
    )

    with pytest.raises(ValueError, match="Unsupported income line update field"):
        service.income_repo.apply_updates(income, {"id": 999})

    with pytest.raises(ValueError, match="Unsupported expense line update field"):
        service.expense_repo.apply_updates(expense, {"created_at": None})


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


def test_audit_scalar_rejects_arbitrary_objects_with_field_context():
    class Unsupported:
        pass

    with pytest.raises(TypeError, match="field 'amount'.*Unsupported"):
        audit_scalar("amount", Unsupported())


def test_audit_scalar_supports_expected_scalar_values():
    assert audit_scalar("source_type", IncomeSourceType.SALARY) == "salary"
    assert audit_scalar("amount", Decimal("100.00")) == "100.00"
    assert audit_scalar("description", "x") == "x"
    assert audit_scalar("count", 1) == 1
    assert audit_scalar("ratio", 1.5) == 1.5
    assert audit_scalar("flag", True) is True
    assert audit_scalar("x", None) is None


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
