from datetime import date, timedelta

from app.advance_payments.models.advance_payment import AdvancePaymentStatus
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.clients.models.client_record import ClientRecord
from app.core.pagination import MAX_PAGE_SIZE
from app.tasks.models.task import Task, TaskStatus
from app.utils.time_utils import utcnow
from app.work_queue.schemas.work_queue import WorkQueueSourceType
from app.work_queue.services.work_queue_common import source_route
from app.work_queue.services.work_queue_service import WorkQueueService
from tests.helpers.identity import seed_client_identity
from tests.helpers.task_helpers import create_business
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def test_work_queue_api_returns_clean_advance_payment_contract(client, test_db, advisor_headers):
    biz = create_business(test_db)
    test_db.get(ClientRecord, biz.client_id).office_client_number = 100001
    due_date = date.today() - timedelta(days=1)
    payment = create_linked_advance_payment(
        test_db,
        client_record_id=biz.client_id,
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


def test_work_queue_api_pagination(client, test_db, advisor_headers):
    from app.charges.models.charge import Charge, ChargeStatus, ChargeType
    from tests.helpers.task_helpers import create_business

    biz = create_business(test_db)
    for days_ago in [31, 32, 33]:
        test_db.add(
            Charge(
                client_record_id=biz.client_id,
                business_id=biz.id,
                amount=100,
                charge_type=ChargeType.OTHER,
                status=ChargeStatus.ISSUED,
                issued_at=date.today() - timedelta(days=days_ago),
            )
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


def test_work_queue_api_page_size_max_enforced(client, advisor_headers):
    response = client.get(
        f"/api/v1/work-queue?page_size={MAX_PAGE_SIZE + 1}",
        headers=advisor_headers,
    )
    assert response.status_code == 422


def test_work_queue_list_summary_not_page_based(client, test_db, advisor_headers):
    test_db.add_all(
        [
            Task(
                title="Open task",
                status=TaskStatus.OPEN,
                created_at=utcnow(),
                updated_at=utcnow(),
            ),
            Task(
                title="Done task",
                status=TaskStatus.DONE,
                created_at=utcnow(),
                updated_at=utcnow(),
            ),
        ]
    )
    test_db.commit()

    active = client.get("/api/v1/work-queue?page_size=1", headers=advisor_headers)
    history = client.get(
        "/api/v1/work-queue?include_task_history=true&page_size=1",
        headers=advisor_headers,
    )

    assert active.status_code == 200
    assert active.json()["total"] == 1
    assert active.json()["summary"]["total"] == 1
    assert active.json()["summary"]["manual_tasks"] == 1
    assert active.json()["summary"]["by_task_status"]["open"] == 1
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["summary"]["total"] == 1
    assert history.json()["summary"]["by_task_status"]["done"] == 1


def test_annual_report_work_queue_route_targets_existing_detail_api(
    client, test_db, advisor_headers
):
    client_record = seed_client_identity(
        test_db, full_name="Work Queue Annual Route", id_number="WQAR001"
    )
    report = AnnualReportService(test_db).create_report(
        client_record_id=client_record.id,
        tax_year=2026,
        client_type="corporation",
        created_by=1,
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
