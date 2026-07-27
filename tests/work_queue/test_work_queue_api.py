from datetime import date, timedelta

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.charges.models.charge import ChargeStatus, ChargeType
from app.clients.models.client_record import ClientRecord
from app.tasks.models.task import TaskStatus
from app.utils.time_utils import utcnow
from app.work_queue.items.common import source_route
from app.work_queue.schemas.work_queue import WorkQueueSourceType
from app.work_queue.services.work_queue_service import WorkQueueService
from tests.helpers.identity import seed_client_identity
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_work_queue_api_returns_clean_advance_payment_contract(
    client, test_db, advisor_headers, create_client_with_business
):
    seeded_client, _biz = create_client_with_business(full_name="Task Test Client")
    test_db.get(ClientRecord, seeded_client.id).office_client_number = 100001
    due_date = date.today() - timedelta(days=1)
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=seeded_client.id,
        period="2026-02",
        due_date=due_date,
        expected_amount=1000,
        paid_amount=250,
    )
    payment.status = AdvancePaymentStatus.PARTIAL
    test_db.commit()

    response = client.get(
        "/api/v1/work-queue?exclude_source_types=vat_work_item&exclude_source_types=annual_report",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    item = next(i for i in response.json()["items"] if i["source_type"] == "advance_payment")
    assert "item_type" not in item
    assert "label" not in item
    assert "payload" not in item
    assert "client_office_number" not in item
    assert item["client_name"].startswith("Task Test Client")
    assert item["office_client_number"] == 100001
    assert item["metadata"]["period"] == "2026-02"
    assert item["metadata"]["period_label"] == "פברואר 2026"
    assert item["metadata"]["frequency"] == "monthly"
    assert item["metadata"]["remaining_amount"] == "750.00"


def test_tasks_route_exists(client, advisor_headers):
    response = client.get("/api/v1/tasks", headers=advisor_headers)

    assert response.status_code == 200


def test_work_queue_api_pagination(
    client, test_db, advisor_headers, create_client_with_business, charge_factory
):
    seeded_client, biz = create_client_with_business()
    for days_ago in [31, 32, 33]:
        charge_factory(
            client=seeded_client,
            business=biz,
            amount=100,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=days_ago),
        )
    test_db.commit()

    r1 = client.get(
        f"/api/v1/work-queue?business_id={biz.id}&page=1&page_size=2",
        headers=advisor_headers,
    )
    r2 = client.get(
        f"/api/v1/work-queue?business_id={biz.id}&page=2&page_size=2",
        headers=advisor_headers,
    )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(r1.json()["items"]) == 2
    assert len(r2.json()["items"]) == 1


def test_work_queue_list_summary_not_page_based(client, test_db, advisor_headers, task_factory):
    task_factory(title="Open task A", status=TaskStatus.OPEN)
    task_factory(title="Open task B", status=TaskStatus.OPEN)
    task_factory(title="Done task", status=TaskStatus.DONE)
    test_db.commit()

    active = client.get("/api/v1/work-queue?page_size=1", headers=advisor_headers)

    assert active.status_code == 200
    # Page returns a single row, but the summary reflects the full filtered set.
    assert len(active.json()["items"]) == 1
    assert active.json()["total"] == 2
    assert active.json()["summary"]["total"] == 2
    assert active.json()["summary"]["manual_tasks"] == 2
    # Done tasks are excluded from the work queue entirely.
    assert active.json()["summary"]["by_task_status"]["open"] == 2
    assert active.json()["summary"]["by_task_status"]["done"] == 0


def test_annual_report_work_queue_route_targets_existing_detail_api(
    client, test_db, advisor_headers, actor_user
):
    client_record = seed_client_identity(
        test_db, full_name="Work Queue Annual Route", id_number="WQAR001"
    )
    report = AnnualReportService(test_db).create_report(
        client_record_id=client_record.id,
        tax_year=2026,
        client_type="corporation",
        created_by=actor_user.id,
        created_by_name="Tester",
        deadline_type="standard",
    )
    report.filing_deadline = utcnow()
    test_db.commit()

    item = next(
        row
        for row in WorkQueueService(test_db).list_items(
            client_record_id=client_record.id,
            source_type=WorkQueueSourceType.ANNUAL_REPORT,
        )
        if row.source_id == report.id
    )

    assert item.available_actions[0].route == f"/tax/reports/{report.id}"
    assert source_route(WorkQueueSourceType.ADVANCE_PAYMENT, 1) == "/tax/advance-payments"

    response = client.get(f"/api/v1/annual-reports/{report.id}", headers=advisor_headers)
    assert response.status_code == 200
