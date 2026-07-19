from datetime import date
from decimal import Decimal

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.search.services.search_service import SearchService
from app.tasks.models.task import Task
from tests.helpers.tax_calendar_links import (
    create_linked_advance_payment,
    create_linked_vat_work_item,
)


def test_operational_search_returns_grouped_client_items(
    test_db,
    test_user,
    create_client_with_business,
    annual_report_factory,
):
    client, _business = create_client_with_business(full_name="אבי הראל")
    task = Task(
        title="השלמת מסמכים 2026",
        client_record_id=client.id,
        created_by_user_id=test_user.id,
    )
    charge = Charge(
        client_record_id=client.id,
        charge_type=ChargeType.ANNUAL_REPORT_FEE,
        status=ChargeStatus.ISSUED,
        amount=Decimal("1500"),
        period="2026-01",
        description="חיוב דוח 2026",
    )
    test_db.add_all([task, charge])
    vat = create_linked_vat_work_item(
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=test_user.id,
    )
    advance = create_linked_advance_payment(
        test_db,
        client_record_id=client.id,
        period="2026-01",
        due_date=date(2026, 2, 15),
        expected_amount=Decimal("800"),
        notes="מקדמת 2026",
    )
    report = annual_report_factory(client=client, actor=test_user, tax_year=2026)
    test_db.commit()

    result = SearchService(test_db).search_operational_items("2026", client.id)

    assert [(item.id, item.client_name) for item in result.tasks.items] == [(task.id, "אבי הראל")]
    assert [item.id for item in result.vat_work_items.items] == [vat.id]
    assert [item.id for item in result.annual_reports.items] == [report.id]
    assert [item.id for item in result.charges.items] == [charge.id]
    assert [item.id for item in result.advance_payments.items] == [advance.id]
    assert all(
        group.total == 1
        for group in (
            result.tasks,
            result.vat_work_items,
            result.annual_reports,
            result.charges,
            result.advance_payments,
        )
    )


def test_operational_search_respects_selected_client_scope(
    test_db, test_user, create_client_with_business
):
    selected, _ = create_client_with_business(full_name="Selected Client")
    other, _ = create_client_with_business(full_name="Other Client")
    test_db.add_all(
        [
            Task(
                title="Shared phrase", client_record_id=selected.id, created_by_user_id=test_user.id
            ),
            Task(title="Shared phrase", client_record_id=other.id, created_by_user_id=test_user.id),
        ]
    )
    test_db.commit()

    result = SearchService(test_db).search_operational_items("shared", selected.id)

    assert result.tasks.total == 1
    assert [item.client_record_id for item in result.tasks.items] == [selected.id]


def test_selected_client_without_text_returns_related_operational_items(
    test_db, test_user, create_client_with_business
):
    selected, _ = create_client_with_business(full_name="Selected Client Preview")
    task = Task(
        title="Latest client task",
        client_record_id=selected.id,
        created_by_user_id=test_user.id,
    )
    test_db.add(task)
    test_db.commit()

    result = SearchService(test_db).search_operational_items(None, selected.id)

    assert result.tasks.total == 1
    assert [item.id for item in result.tasks.items] == [task.id]
