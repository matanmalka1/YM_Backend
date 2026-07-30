from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select

from app.annual_reports.annual_report_financial_line_helpers import audit_scalar
from app.annual_reports.models.annual_report_expense_line import (
    AnnualReportExpenseLine,
    ExpenseCategoryType,
)
from app.annual_reports.models.annual_report_income_line import (
    AnnualReportIncomeLine,
    IncomeSourceType,
)
from app.annual_reports.services.annual_report_financial_line_service import (
    AnnualReportFinancialLineService,
)
from app.audit.audit_constants import (
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_EXPENSE_UPDATED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ACTION_INCOME_UPDATED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.core.exceptions import NotFoundError

_seq = count(1)


def _audit_entries(db, report_id: int, action: str) -> list[EntityAuditLog]:
    return db.scalars(
        select(EntityAuditLog)
        .filter(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .filter(EntityAuditLog.entity_id == report_id)
        .filter(EntityAuditLog.action == action)
    ).all()


def test_income_delete_stores_old_value_snapshot(test_db, test_user, annual_report_service_factory):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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
    assert entry.old_value == {
        "line_id": line.id,
        "source_type": "salary",
        "amount": "123.45",
        "description": "Payroll",
    }


def test_manual_financial_mutation_blocks_missing_client_record(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    ClientRecordRepository(test_db).soft_delete(report.client_record_id, deleted_by=test_user.id)
    service = AnnualReportFinancialLineService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.add_income(
            report.id,
            "salary",
            Decimal("100.00"),
            actor_id=test_user.id,
        )

    assert exc_info.value.code == "CLIENT_RECORD.NOT_FOUND"


def test_expense_delete_stores_old_value_snapshot(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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
    assert entry.old_value == {
        "line_id": line.id,
        "category": "office_rent",
        "amount": "456.78",
        "recognition_rate": "1.00",
        "external_document_reference": None,
        "supporting_document_id": None,
        "description": "Rent",
    }


def test_income_add_stores_snapshot_payload(test_db, test_user, annual_report_service_factory):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
    line = service.add_income(
        report.id,
        "salary",
        Decimal("123.45"),
        description="Payroll",
        actor_id=test_user.id,
    )

    entry = _audit_entries(test_db, report.id, ACTION_INCOME_ADDED)[0]

    assert entry.new_value == {
        "line_id": line.id,
        "source_type": "salary",
        "amount": "123.45",
        "description": "Payroll",
    }


def test_expense_add_stores_full_snapshot_payload(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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

    assert entry.new_value == {
        "line_id": line.id,
        "category": "office_rent",
        "amount": "456.78",
        "recognition_rate": "0.75",
        "external_document_reference": "INV-100",
        "supporting_document_id": None,
        "description": "Rent",
    }


def test_income_update_audit_records_only_sent_fields(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
    line = service.add_income(
        report.id,
        "salary",
        Decimal("500.00"),
        description="Payroll",
        actor_id=test_user.id,
    )

    # Only `amount` is sent (exclude_unset); `description` is untouched.
    service.update_income(
        report.id,
        line.id,
        actor_id=test_user.id,
        amount=Decimal("600.00"),
    )

    entry = _audit_entries(test_db, report.id, ACTION_INCOME_UPDATED)[0]
    assert entry.new_value == {"amount": "600.00"}


def test_income_update_explicit_null_clears_nullable_description(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
    line = service.add_income(
        report.id,
        "salary",
        Decimal("500.00"),
        description="Payroll",
        actor_id=test_user.id,
    )

    # Explicit null on a nullable field clears it (true partial PATCH).
    service.update_income(
        report.id,
        line.id,
        actor_id=test_user.id,
        description=None,
    )

    refreshed = test_db.get(AnnualReportIncomeLine, line.id)
    assert refreshed.description is None
    entry = _audit_entries(test_db, report.id, ACTION_INCOME_UPDATED)[0]
    assert entry.new_value == {"description": None}


def test_expense_update_audit_stores_full_old_snapshot_and_sent_fields(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
    line = service.add_expense(
        report.id,
        "office_rent",
        Decimal("500.00"),
        description="Rent",
        recognition_rate=Decimal("0.50"),
        external_document_reference="INV-OLD",
        actor_id=test_user.id,
    )

    # recognition_rate updated; description explicitly cleared (nullable column).
    service.update_expense(
        report.id,
        line.id,
        actor_id=test_user.id,
        recognition_rate=Decimal("0.75"),
        description=None,
    )

    entry = _audit_entries(test_db, report.id, ACTION_EXPENSE_UPDATED)[0]
    assert entry.old_value == {
        "line_id": line.id,
        "category": "office_rent",
        "amount": "500.00",
        "recognition_rate": "0.50",
        "external_document_reference": "INV-OLD",
        "supporting_document_id": None,
        "description": "Rent",
    }
    assert entry.new_value == {"recognition_rate": "0.75", "description": None}
    refreshed = test_db.get(AnnualReportExpenseLine, line.id)
    assert refreshed.description is None


def test_financial_line_updates_with_no_sent_fields_do_not_write_audit(
    test_db, test_user, annual_report_service_factory
):
    # A truly empty PATCH ({}) is rejected at the schema layer by
    # NonEmptyUpdateMixin before reaching the service. At the service boundary,
    # passing no update fields is a no-op that writes no audit entry.
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
    income = service.add_income(report.id, "salary", Decimal("500.00"), actor_id=test_user.id)
    expense = service.add_expense(
        report.id,
        "office_rent",
        Decimal("500.00"),
        actor_id=test_user.id,
    )

    service.update_income(report.id, income.id, actor_id=test_user.id)
    service.update_expense(report.id, expense.id, actor_id=test_user.id)

    assert _audit_entries(test_db, report.id, ACTION_INCOME_UPDATED) == []
    assert _audit_entries(test_db, report.id, ACTION_EXPENSE_UPDATED) == []


def test_financial_line_repositories_reject_unsupported_update_fields(
    test_db, test_user, annual_report_service_factory
):
    report = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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


def test_cannot_update_income_line_from_another_report(
    test_db, test_user, annual_report_service_factory
):
    report_a = annual_report_service_factory(actor=test_user)
    report_b = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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


def test_cannot_delete_income_line_from_another_report(
    test_db, test_user, annual_report_service_factory
):
    report_a = annual_report_service_factory(actor=test_user)
    report_b = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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


def test_cannot_update_expense_line_from_another_report(
    test_db, test_user, annual_report_service_factory
):
    report_a = annual_report_service_factory(actor=test_user)
    report_b = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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


def test_cannot_delete_expense_line_from_another_report(
    test_db, test_user, annual_report_service_factory
):
    report_a = annual_report_service_factory(actor=test_user)
    report_b = annual_report_service_factory(actor=test_user)
    service = AnnualReportFinancialLineService(test_db)
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
