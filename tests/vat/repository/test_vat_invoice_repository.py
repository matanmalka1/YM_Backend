from datetime import UTC, date, datetime
from itertools import count

from app.businesses.models.business import Business
from app.common.enums import VatType
from app.users.models.user import User, UserRole
from app.vat.models.vat_enums import (
    DocumentType,
    ExpenseCategory,
    InvoiceType,
    VatRateType,
)
from app.vat.repositories.vat_invoice_repository import VatInvoiceRepository
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from tests.factories import create_user
from tests.helpers.identity import seed_client_with_business
from tests.helpers.tax_calendar_links import create_linked_vat_work_item

_client_seq = count(1)


def _user(test_db) -> User:
    user = create_user(
        test_db,
        full_name="VAT Repo User",
        email="vat.repo@example.com",
        password="pass",
        role=UserRole.ADVISOR,
        is_active=True,
        commit=True,
    )
    return user


def _business(db) -> tuple[Business, int]:
    idx = next(_client_seq)
    client, business = seed_client_with_business(
        db,
        full_name=f"VAT Repo Client {idx}",
        id_number=f"VRI{idx:03d}",
        opened_at=date(2026, 1, 1),
    )
    db.commit()
    db.refresh(business)
    return business, client.id


def test_list_by_work_item_orders_and_filters_by_type(test_db):
    user = _user(test_db)
    business, client_record_id = _business(test_db)
    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-05",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    other_item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-06",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    expense = invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-001",
        invoice_date=datetime(2026, 5, 1),
        counterparty_name="Vendor",
        counterparty_id="EXP-CP",
        net_amount=500.0,
        vat_amount=85.0,
        expense_category=ExpenseCategory.OFFICE,
    )
    income = invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-001",
        invoice_date=datetime(2026, 5, 3),
        counterparty_name="Customer",
        net_amount=1000.0,
        vat_amount=170.0,
    )
    invoice_repo.create(
        work_item_id=other_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-OTHER",
        invoice_date=datetime(2026, 5, 2),
        counterparty_name="Other",
        net_amount=200.0,
        vat_amount=34.0,
    )

    all_for_item = invoice_repo.list_by_work_item(item.id)
    assert [inv.id for inv in all_for_item] == [expense.id, income.id]

    income_only = invoice_repo.list_by_work_item(item.id, invoice_type=InvoiceType.INCOME)
    assert [inv.id for inv in income_only] == [income.id]


def test_sum_income_net_by_business_year_filters_by_business_year_and_income_only(
    test_db,
):
    user = _user(test_db)
    business, client_record_id = _business(test_db)
    other_business, other_client_record_id = _business(test_db)

    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    target_item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    previous_year_item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2025-12",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    other_business_item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=other_client_record_id,
        period="2026-02",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    invoice_repo.create(
        work_item_id=target_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-YEAR-1",
        invoice_date=datetime(2026, 1, 5),
        counterparty_name="Customer A",
        net_amount=1000.0,
        vat_amount=170.0,
    )
    invoice_repo.create(
        work_item_id=target_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-YEAR-IGNORED",
        invoice_date=datetime(2026, 1, 8),
        counterparty_name="Vendor A",
        net_amount=400.0,
        vat_amount=68.0,
        expense_category=ExpenseCategory.OFFICE,
    )
    invoice_repo.create(
        work_item_id=previous_year_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-OTHER-YEAR",
        invoice_date=datetime(2025, 12, 25),
        counterparty_name="Customer B",
        net_amount=300.0,
        vat_amount=51.0,
    )
    invoice_repo.create(
        work_item_id=other_business_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-OTHER-BUSINESS",
        invoice_date=datetime(2026, 2, 3),
        counterparty_name="Customer C",
        net_amount=700.0,
        vat_amount=119.0,
    )

    assert invoice_repo.sum_income_net_by_client_year(client_record_id, 2026) == 1000.0
    assert invoice_repo.sum_income_net_by_client_year(client_record_id, 2024) == 0.0


def test_sum_income_net_excludes_soft_deleted_work_items(test_db):
    user = _user(test_db)
    business, client_record_id = _business(test_db)

    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    active_item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-03",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    deleted_item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-04",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    invoice_repo.create(
        work_item_id=active_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-ACTIVE",
        invoice_date=datetime(2026, 3, 1),
        counterparty_name="Customer A",
        net_amount=5000.0,
        vat_amount=850.0,
    )
    invoice_repo.create(
        work_item_id=deleted_item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-DELETED",
        invoice_date=datetime(2026, 4, 1),
        counterparty_name="Customer B",
        net_amount=9000.0,
        vat_amount=1530.0,
    )

    # Soft-delete the second work item directly
    deleted_item.deleted_at = datetime.now(UTC)
    test_db.commit()

    # Only the active item's invoices should count toward the ceiling
    assert invoice_repo.sum_income_net_by_client_year(client_record_id, 2026) == 5000.0


def test_sum_vat_and_net_both_types_aggregate_in_single_result_set(test_db):
    user = _user(test_db)
    business, client_record_id = _business(test_db)
    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-07",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-STD",
        invoice_date=datetime(2026, 7, 1),
        counterparty_name="Customer A",
        net_amount=1000.0,
        vat_amount=170.0,
        rate_type=VatRateType.STANDARD,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-ZERO",
        invoice_date=datetime(2026, 7, 2),
        counterparty_name="Customer B",
        net_amount=400.0,
        vat_amount=68.0,
        rate_type=VatRateType.ZERO_RATE,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-ONE",
        invoice_date=datetime(2026, 7, 3),
        counterparty_name="Vendor A",
        net_amount=500.0,
        vat_amount=85.0,
        expense_category=ExpenseCategory.OFFICE,
        deduction_rate=1.0,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-TWO",
        invoice_date=datetime(2026, 7, 4),
        counterparty_name="Vendor B",
        net_amount=200.0,
        vat_amount=34.0,
        expense_category=ExpenseCategory.VEHICLE,
        deduction_rate=0.5,
    )

    assert invoice_repo.sum_vat_both_types(item.id) == (170.0, 102.0)
    assert invoice_repo.sum_net_both_types(item.id) == (1400.0, 700.0)


def test_credit_notes_reduce_vat_and_net_totals(test_db):
    user = _user(test_db)
    business, client_record_id = _business(test_db)
    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-08",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-BASE",
        invoice_date=datetime(2026, 8, 1),
        counterparty_name="Customer A",
        net_amount=1000.0,
        vat_amount=170.0,
        rate_type=VatRateType.STANDARD,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-CN",
        invoice_date=datetime(2026, 8, 2),
        counterparty_name="Customer A",
        net_amount=200.0,
        vat_amount=34.0,
        rate_type=VatRateType.STANDARD,
        document_type=DocumentType.CREDIT_NOTE,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-BASE",
        invoice_date=datetime(2026, 8, 3),
        counterparty_name="Vendor A",
        net_amount=500.0,
        vat_amount=85.0,
        expense_category=ExpenseCategory.OFFICE,
        deduction_rate=1.0,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-CN",
        invoice_date=datetime(2026, 8, 4),
        counterparty_name="Vendor A",
        net_amount=100.0,
        vat_amount=17.0,
        expense_category=ExpenseCategory.OFFICE,
        deduction_rate=1.0,
        document_type=DocumentType.CREDIT_NOTE,
    )

    assert invoice_repo.sum_vat_both_types(item.id) == (136.0, 68.0)
    assert invoice_repo.sum_net_both_types(item.id) == (800.0, 400.0)


def test_credit_notes_reduce_income_turnover_for_yearly_ceiling(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)

    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-09",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-TURNOVER",
        invoice_date=datetime(2026, 9, 1),
        counterparty_name="Customer A",
        net_amount=1000.0,
        vat_amount=170.0,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.INCOME,
        invoice_number="INC-TURNOVER-CN",
        invoice_date=datetime(2026, 9, 2),
        counterparty_name="Customer A",
        net_amount=250.0,
        vat_amount=42.5,
        document_type=DocumentType.CREDIT_NOTE,
    )

    assert invoice_repo.sum_income_net_by_client_year(client_record_id, 2026) == 750.0


def test_credit_notes_reduce_grouped_expense_totals(test_db):
    user = _user(test_db)
    _, client_record_id = _business(test_db)

    work_item_repo = VatWorkItemRepository(test_db)
    invoice_repo = VatInvoiceRepository(test_db)

    item = create_linked_vat_work_item(
        test_db,
        repo=work_item_repo,
        client_record_id=client_record_id,
        period="2026-10",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )

    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-GROUP-1",
        invoice_date=datetime(2026, 10, 1),
        counterparty_name="Vendor A",
        net_amount=600.0,
        vat_amount=102.0,
        expense_category=ExpenseCategory.OFFICE,
    )
    invoice_repo.create(
        work_item_id=item.id,
        created_by=user.id,
        invoice_type=InvoiceType.EXPENSE,
        invoice_number="EXP-GROUP-CN",
        invoice_date=datetime(2026, 10, 2),
        counterparty_name="Vendor A",
        net_amount=150.0,
        vat_amount=25.5,
        expense_category=ExpenseCategory.OFFICE,
        document_type=DocumentType.CREDIT_NOTE,
    )

    assert invoice_repo.sum_expense_net_by_client_year_grouped(client_record_id, 2026) == {
        "office": 450.0
    }


def test_update_and_delete_return_falsy_for_missing_invoice(test_db):
    repo = VatInvoiceRepository(test_db)

    assert repo.update(999999, invoice_number="NOPE") is None
    assert repo.delete(999999) is False
