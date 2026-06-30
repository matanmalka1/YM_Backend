from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.annual_reports.services.annual_report_financial_line_service import (
    AnnualReportFinancialLineService,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.annual_reports.services.annual_report_vat_import_service import VatImportService
from app.audit.audit_constants import (
    ACTION_EXPENSE_ADDED,
    ACTION_EXPENSE_DELETED,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ENTITY_ANNUAL_REPORT,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.common.enums import VatType
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.vat.models.vat_enums import ExpenseCategory, InvoiceType, VatWorkItemStatus
from app.vat.models.vat_invoice import VatInvoice
from app.vat.models.vat_work_item import VatWorkItem
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _create_report(db, user, suffix: str = "1"):
    client = seed_client_identity(
        db,
        full_name=f"VAT Import Client {suffix}",
        id_number=f"VATIMP{suffix}",
    )
    report = AnnualReportService(db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="corporation",
        created_by=user.id,
        created_by_name=user.full_name,
    )
    return client, report


def _audit_payloads(db, report_id: int, action: str, field: str) -> list[dict]:
    rows = db.scalars(
        select(EntityAuditLog)
        .where(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
        .where(EntityAuditLog.entity_id == report_id)
        .where(EntityAuditLog.action == action)
        .order_by(EntityAuditLog.id.asc())
    ).all()
    return [getattr(row, field) for row in rows if getattr(row, field)]


def _audit_rows(db, report_id: int, action: str) -> list[EntityAuditLog]:
    return list(
        db.scalars(
            select(EntityAuditLog)
            .where(EntityAuditLog.entity_type == ENTITY_ANNUAL_REPORT)
            .where(EntityAuditLog.entity_id == report_id)
            .where(EntityAuditLog.action == action)
            .order_by(EntityAuditLog.id.asc())
        ).all()
    )


def test_vat_auto_populate_writes_audit_and_source_breakdown(test_db, test_user, monkeypatch):
    _, report = _create_report(test_db, test_user, "A")
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("1000.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {
            "fuel": Decimal("800.00"),
            "vehicle_maintenance": Decimal("400.00"),
            "office": Decimal("250.00"),
        },
    )

    result = service.auto_populate(report.id, actor_id=test_user.id)

    assert result["income_lines_created"] == 1
    assert result["expense_lines_created"] == 2
    vehicle = next(
        item for item in result["expense_breakdown"] if item["annual_category"] == "vehicle"
    )
    assert vehicle["amount"] == Decimal("1200.00")
    assert vehicle["source_vat_categories"] == {
        "fuel": Decimal("800.00"),
        "vehicle_maintenance": Decimal("400.00"),
    }

    income_payload = _audit_payloads(test_db, report.id, ACTION_INCOME_ADDED, "new_value")[0]
    assert income_payload["source"] == "vat_import"
    assert income_payload["amount"] == "1000.00"
    income_entry = _audit_rows(test_db, report.id, ACTION_INCOME_ADDED)[0]
    assert income_entry.metadata_json["section"] == "income"
    assert income_entry.metadata_json["line_id"] == income_payload["line_id"]

    expense_payloads = _audit_payloads(test_db, report.id, ACTION_EXPENSE_ADDED, "new_value")
    vehicle_payload = next(
        payload for payload in expense_payloads if payload["category"] == "vehicle"
    )
    assert vehicle_payload["source"] == "vat_import"
    assert vehicle_payload["source_vat_categories"] == {
        "fuel": "800.00",
        "vehicle_maintenance": "400.00",
    }
    expense_entry = next(
        row
        for row in _audit_rows(test_db, report.id, ACTION_EXPENSE_ADDED)
        if row.new_value["category"] == "vehicle"
    )
    assert expense_entry.metadata_json["section"] == "expense"
    assert expense_entry.metadata_json["line_id"] == vehicle_payload["line_id"]


def test_vat_auto_populate_force_audits_replaced_lines(test_db, test_user, monkeypatch):
    _, report = _create_report(test_db, test_user, "B")
    financial = AnnualReportFinancialLineService(test_db)
    financial.add_income(report.id, "salary", Decimal("500.00"), actor_id=test_user.id)
    financial.add_expense(report.id, "office_rent", Decimal("300.00"), actor_id=test_user.id)
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("700.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {"office": Decimal("200.00")},
    )

    result = service.auto_populate(report.id, force=True, actor_id=test_user.id)

    assert result["lines_deleted"] == 2
    deleted_income = _audit_payloads(test_db, report.id, ACTION_INCOME_DELETED, "old_value")[0]
    deleted_expense = _audit_payloads(test_db, report.id, ACTION_EXPENSE_DELETED, "old_value")[0]
    assert deleted_income["mutation_source"] == "vat_import"
    assert deleted_income["mutation_reason"] == "force_replace"
    assert "source" not in deleted_income
    assert deleted_expense["mutation_source"] == "vat_import"
    assert deleted_expense["mutation_reason"] == "force_replace"
    assert "source" not in deleted_expense


def test_vat_auto_populate_skips_zero_and_negative_totals(test_db, test_user, monkeypatch):
    _, report = _create_report(test_db, test_user, "C")
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("-50.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {
            "fuel": Decimal("100.00"),
            "vehicle_maintenance": Decimal("-100.00"),
            "office": Decimal("-25.00"),
        },
    )

    result = service.auto_populate(report.id, actor_id=test_user.id)

    assert result["income_lines_created"] == 0
    assert result["expense_lines_created"] == 0
    assert result["income_total"] == Decimal("0")
    assert result["expense_total"] == Decimal("0")
    skipped = result["skipped_items"]
    assert {
        "item_type": "income",
        "source": "business",
        "amount": Decimal("-50.00"),
        "reason": "negative_total",
        "annual_category": None,
    } in skipped
    assert any(
        item["item_type"] == "expense"
        and item["annual_category"] == "vehicle"
        and item["reason"] == "zero_total"
        for item in skipped
    )
    assert any(
        item["item_type"] == "expense"
        and item["annual_category"] == "office_rent"
        and item["reason"] == "negative_total"
        for item in skipped
    )
    assert len(result["warnings"]) == 2


def test_vat_auto_populate_surfaces_negative_source_inside_positive_merge(
    test_db, test_user, monkeypatch
):
    _, report = _create_report(test_db, test_user, "M")
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("0.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {
            "fuel": Decimal("-100.00"),
            "vehicle_maintenance": Decimal("300.00"),
        },
    )

    result = service.auto_populate(report.id, actor_id=test_user.id)

    assert result["expense_lines_created"] == 1
    assert result["expense_total"] == Decimal("200.00")
    assert {
        "item_type": "expense",
        "source": "fuel",
        "amount": Decimal("-100.00"),
        "reason": "negative_source_contribution",
        "annual_category": "vehicle",
    } in result["skipped_items"]
    assert result["warnings"] == [
        "VAT import included negative source category fuel under vehicle; review credits or corrections."
    ]


def test_vat_auto_populate_empty_vat_data_has_no_skipped_noise(test_db, test_user, monkeypatch):
    _, report = _create_report(test_db, test_user, "Z")
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("0.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {},
    )

    result = service.auto_populate(report.id, actor_id=test_user.id)

    assert result["income_lines_created"] == 0
    assert result["expense_lines_created"] == 0
    assert result["skipped_items"] == []
    assert result["warnings"] == []


def test_vat_auto_populate_requires_actor_for_audited_mutation(test_db, test_user, monkeypatch):
    _, report = _create_report(test_db, test_user, "N")
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("100.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {},
    )

    with pytest.raises(AppError) as exc_info:
        service.auto_populate(report.id, actor_id=None)

    assert exc_info.value.code == "ANNUAL_REPORT.AUDIT_ACTOR_REQUIRED"


def test_vat_auto_populate_blocks_missing_client_record(test_db, test_user):
    client, report = _create_report(test_db, test_user, "MISSING")
    ClientRecordRepository(test_db).soft_delete(client.id, deleted_by=test_user.id)
    service = VatImportService(test_db)

    with pytest.raises(NotFoundError) as exc_info:
        service.auto_populate(report.id, force=True, actor_id=test_user.id)

    assert exc_info.value.code == "CLIENT_RECORD.NOT_FOUND"


@pytest.mark.parametrize("status", [ClientStatus.CLOSED, ClientStatus.FROZEN])
def test_vat_auto_populate_blocks_closed_or_frozen_clients_even_force(
    test_db, test_user, monkeypatch, status
):
    client, report = _create_report(test_db, test_user, f"D{status.value}")
    financial = AnnualReportFinancialLineService(test_db)
    financial.add_income(report.id, "salary", Decimal("500.00"), actor_id=test_user.id)
    client_record = test_db.get(ClientRecord, client.id)
    client_record.status = status
    test_db.flush()
    service = VatImportService(test_db)
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_income_net_by_client_year",
        lambda *args: Decimal("700.00"),
    )
    monkeypatch.setattr(
        service.vat_agg_repo,
        "sum_expense_net_by_client_year_grouped",
        lambda *args: {},
    )

    with pytest.raises(ForbiddenError) as exc_info:
        service.auto_populate(report.id, force=True, actor_id=test_user.id)

    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"
    result_count = len(financial.income_repo.list_by_report(report.id))
    assert result_count == 1


@pytest.mark.parametrize("status", [ClientStatus.CLOSED, ClientStatus.FROZEN])
def test_manual_financial_mutations_block_closed_or_frozen_clients(test_db, test_user, status):
    client, report = _create_report(test_db, test_user, f"E{status.value}")
    financial = AnnualReportFinancialLineService(test_db)
    income = financial.add_income(report.id, "salary", Decimal("500.00"), actor_id=test_user.id)
    expense = financial.add_expense(
        report.id,
        "office_rent",
        Decimal("300.00"),
        actor_id=test_user.id,
    )
    client_record = test_db.get(ClientRecord, client.id)
    client_record.status = status
    test_db.flush()

    with pytest.raises(ForbiddenError) as exc_info:
        financial.add_income(report.id, "salary", Decimal("100.00"), actor_id=test_user.id)
    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"
    with pytest.raises(ForbiddenError) as exc_info:
        financial.add_expense(report.id, "office_rent", Decimal("100.00"), actor_id=test_user.id)
    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"
    with pytest.raises(ForbiddenError) as exc_info:
        financial.update_income(
            report.id,
            income.id,
            actor_id=test_user.id,
            amount=Decimal("600.00"),
        )
    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"
    with pytest.raises(ForbiddenError) as exc_info:
        financial.update_expense(
            report.id,
            expense.id,
            actor_id=test_user.id,
            amount=Decimal("400.00"),
        )
    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"
    with pytest.raises(ForbiddenError) as exc_info:
        financial.delete_income(report.id, income.id, actor_id=test_user.id)
    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"
    with pytest.raises(ForbiddenError) as exc_info:
        financial.delete_expense(report.id, expense.id, actor_id=test_user.id)
    assert exc_info.value.code == f"CLIENT.{status.value.upper()}"

    assert financial.income_repo.get_by_report_and_line_id(report.id, income.id).amount == Decimal(
        "500.00"
    )
    assert financial.expense_repo.get_by_report_and_line_id(
        report.id, expense.id
    ).amount == Decimal("300.00")


def _seed_vat_work_item(db, client_record_id: int, period: str, user_id: int) -> VatWorkItem:
    return create_linked_vat_work_item(
        db,
        client_record_id=client_record_id,
        period=period,
        period_type=VatType.MONTHLY,
        created_by=user_id,
        status=VatWorkItemStatus.MATERIAL_RECEIVED,
    )


def _seed_vat_invoice(
    db,
    work_item_id: int,
    user_id: int,
    invoice_type: InvoiceType,
    net_amount: Decimal,
    invoice_number: str,
    expense_category: ExpenseCategory | None = None,
    business_id: int | None = None,
) -> VatInvoice:
    inv = VatInvoice(
        work_item_id=work_item_id,
        created_by=user_id,
        business_activity_id=business_id,
        invoice_type=invoice_type,
        invoice_number=invoice_number,
        invoice_date=date(2026, 3, 1),
        counterparty_name="Test Counterparty",
        net_amount=net_amount,
        vat_amount=Decimal("0.00"),
        expense_category=expense_category,
    )
    db.add(inv)
    db.flush()
    return inv


def test_vat_auto_populate_aggregates_all_businesses_for_client_year(test_db, test_user):
    """VAT auto-populate is intentionally client-wide.

    Annual reports are scoped to client_record_id + tax_year, not to a business.
    auto_populate must aggregate VAT across all businesses belonging to the same
    client_record_id and tax_year, regardless of business_activity_id on invoices.
    """
    client = seed_client_identity(
        test_db,
        full_name="Multi Business Client",
        id_number="MULTIBIZ001",
    )
    biz_a = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Business A",
    )
    biz_b = seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name="Business B",
    )

    report = AnnualReportService(test_db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="self_employed",
        created_by=test_user.id,
        created_by_name=test_user.full_name,
    )

    item_a = _seed_vat_work_item(test_db, client.id, "2026-01", test_user.id)
    item_b = _seed_vat_work_item(test_db, client.id, "2026-02", test_user.id)

    _seed_vat_invoice(
        test_db,
        item_a.id,
        test_user.id,
        InvoiceType.INCOME,
        Decimal("3000.00"),
        "INV-A1",
        business_id=biz_a.id,
    )
    _seed_vat_invoice(
        test_db,
        item_b.id,
        test_user.id,
        InvoiceType.INCOME,
        Decimal("2000.00"),
        "INV-B1",
        business_id=biz_b.id,
    )
    _seed_vat_invoice(
        test_db,
        item_a.id,
        test_user.id,
        InvoiceType.EXPENSE,
        Decimal("500.00"),
        "EXP-A1",
        expense_category=ExpenseCategory.OFFICE,
        business_id=biz_a.id,
    )
    _seed_vat_invoice(
        test_db,
        item_b.id,
        test_user.id,
        InvoiceType.EXPENSE,
        Decimal("300.00"),
        "EXP-B1",
        expense_category=ExpenseCategory.OFFICE,
        business_id=biz_b.id,
    )
    test_db.flush()

    result = VatImportService(test_db).auto_populate(report.id, actor_id=test_user.id)

    assert result["income_lines_created"] == 1
    assert result["income_total"] == Decimal("5000.00"), (
        "Expected sum of both businesses' income (3000+2000); "
        "auto_populate is intentionally client-wide, not per-business."
    )
    assert result["expense_lines_created"] == 1
    assert result["expense_total"] == Decimal("800.00"), (
        "Expected sum of both businesses' office expenses (500+300)."
    )
