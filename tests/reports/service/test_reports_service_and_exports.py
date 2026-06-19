import os
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import event

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.reports.advance_payment_report import AdvancePaymentReportService
from app.reports.services.report_export_service import ExportService
from app.reports.services.report_service import AgingReportService
from tests.helpers.identity import seed_client_with_business
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def _client_and_business(db, suffix: str):
    client, business = seed_client_with_business(
        db,
        full_name=f"Aging Service Client {suffix}",
        id_number=f"{100000000 + int(suffix):09d}",
        business_name=f"Aging Service Client {suffix}",
        opened_at=date.today(),
    )
    db.commit()
    return client, business


def _charge(db, client_record_id: int, business_id: int, amount: str, issued_days_ago: int):
    issued_at = date.today() - timedelta(days=issued_days_ago)
    charge = Charge(
        client_record_id=client_record_id,
        business_id=business_id,
        amount=Decimal(amount),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        issued_at=issued_at,
        created_at=issued_at,
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)
    return charge


def test_aging_report_service_calculates_buckets(test_db):
    c, b = _client_and_business(test_db, "1")
    _charge(test_db, c.id, b.id, "100.00", 5)
    _charge(test_db, c.id, b.id, "200.00", 40)
    _charge(test_db, c.id, b.id, "300.00", 70)
    _charge(test_db, c.id, b.id, "400.00", 120)

    report = AgingReportService(test_db).generate_aging_report()

    assert report["total_outstanding"] == 1000.0
    assert report["summary"]["total_current"] == 100.0
    assert report["summary"]["total_30_days"] == 200.0
    assert report["summary"]["total_60_days"] == 300.0
    assert report["summary"]["total_90_plus"] == 400.0


def test_aging_report_service_batches_client_name_lookup(test_db):
    for suffix in range(10, 18):
        c, b = _client_and_business(test_db, str(suffix))
        _charge(test_db, c.id, b.id, "100.00", 45)

    query_count = 0

    def track_query(*_args):
        nonlocal query_count
        query_count += 1

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        report = AgingReportService(test_db).generate_aging_report(page=1, page_size=8)
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert len(report["items"]) == 8
    assert query_count <= 6


def test_export_service_generates_excel_and_pdf_files(test_db):
    c, b = _client_and_business(test_db, "2")
    _charge(test_db, c.id, b.id, "150.00", 20)

    report_data = AgingReportService(test_db).generate_aging_report()
    exporter = ExportService()

    excel = exporter.export_aging_report_to_excel(report_data)
    pdf = exporter.export_aging_report_to_pdf(report_data)

    assert excel["format"] == "excel"
    assert pdf["format"] == "pdf"
    assert os.path.exists(excel["filepath"])
    assert os.path.exists(pdf["filepath"])


def test_aging_report_service_skips_rows_without_matching_business(test_db):
    service = AgingReportService(test_db)

    service.charge_repo = SimpleNamespace(
        get_aging_buckets_paginated=lambda as_of_date, *, page, page_size: (
            [
                {
                    "client_record_id": 999_999,
                    "total": 100,
                    "current": 100,
                    "days_30": 0,
                    "days_60": 0,
                    "days_90_plus": 0,
                    "oldest_issued_at": None,
                }
            ],
            1,
        ),
        get_aging_totals=lambda as_of_date: SimpleNamespace(
            total_clients=0,
            total_current=0,
            total_30_days=0,
            total_60_days=0,
            total_90_plus=0,
            grand_total=0,
        ),
    )
    service.client_record_repo = SimpleNamespace(list_by_ids=lambda ids: [])

    report = service.generate_aging_report(as_of_date=date(2026, 3, 1))

    assert report["items"] == []
    assert report["total_outstanding"] == 0.0
    assert report["summary"]["total_clients"] == 0


def test_advance_payment_report_uses_client_record_legal_entity_names(test_db):
    service = AdvancePaymentReportService(test_db)
    service.repo = SimpleNamespace(
        get_collections_aggregates=lambda year, month: [
            SimpleNamespace(
                client_record_id=7,
                total_expected=Decimal("300.00"),
                total_paid=Decimal("120.00"),
                overdue_count=2,
            )
        ]
    )
    service.client_record_repo = SimpleNamespace(
        list_by_ids=lambda ids: [
            SimpleNamespace(id=7, legal_entity_id=70, office_client_number=101234)
        ]
    )
    service.legal_entity_repo = SimpleNamespace(
        list_by_ids=lambda ids: [SimpleNamespace(id=70, official_name="Advance Client")]
    )

    report = service.get_collections_report(year=2026, month=3)

    assert report["items"] == [
        {
            "client_record_id": 7,
            "office_client_number": 101234,
            "client_name": "Advance Client",
            "total_expected": 300.0,
            "total_paid": 120.0,
            "overdue_count": 2,
            "gap": 180.0,
        }
    ]


def test_advance_payment_report_batches_client_name_lookup(test_db):
    for suffix in range(20, 28):
        client, _business = _client_and_business(test_db, str(suffix))
        create_linked_advance_payment(
            test_db,
            client_record_id=client.id,
            period="2026-01",
            due_date=date(2026, 2, 15),
            expected_amount=Decimal("100.00"),
            paid_amount=Decimal("25.00"),
        )
    test_db.commit()

    query_count = 0

    def track_query(*_args):
        nonlocal query_count
        query_count += 1

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        report = AdvancePaymentReportService(test_db).get_collections_report(
            year=2026,
            month=1,
        )
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert len(report["items"]) == 8
    assert query_count <= 3
