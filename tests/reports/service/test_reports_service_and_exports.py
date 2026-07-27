import os
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import event

from app.charges.models.charge import ChargeStatus, ChargeType
from app.reports.advance_payment_report import AdvancePaymentReportService
from app.reports.services.report_export_service import ExportService
from app.reports.services.report_service import AgingReportService
from tests.helpers.tax_calendar_links import create_linked_advance_payment


def _charge(
    charge_factory, client_record_id: int, business_id: int, amount: str, issued_days_ago: int
):
    issued_at = date.today() - timedelta(days=issued_days_ago)
    return charge_factory(
        client_record_id=client_record_id,
        business_id=business_id,
        amount=Decimal(amount),
        charge_type=ChargeType.CONSULTATION_FEE,
        status=ChargeStatus.ISSUED,
        issued_at=issued_at,
        commit=True,
    )


def test_aging_report_service_calculates_buckets(
    test_db, create_client_with_business, charge_factory
):
    c, b = create_client_with_business()
    _charge(charge_factory, c.id, b.id, "100.00", 5)
    _charge(charge_factory, c.id, b.id, "200.00", 40)
    _charge(charge_factory, c.id, b.id, "300.00", 70)
    _charge(charge_factory, c.id, b.id, "400.00", 120)

    report = AgingReportService(test_db).generate_aging_report()

    assert report["total_outstanding"] == 1000.0
    assert report["summary"]["total_current"] == 100.0
    assert report["summary"]["total_30_days"] == 200.0
    assert report["summary"]["total_60_days"] == 300.0
    assert report["summary"]["total_90_plus"] == 400.0


def test_aging_report_service_batches_client_name_lookup(
    test_db, create_client_with_business, charge_factory
):
    for _suffix in range(10, 18):
        c, b = create_client_with_business()
        _charge(charge_factory, c.id, b.id, "100.00", 45)

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


def test_export_service_generates_excel_and_pdf_files(
    test_db, create_client_with_business, charge_factory
):
    c, b = create_client_with_business()
    _charge(charge_factory, c.id, b.id, "150.00", 20)

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
        get_aging_buckets_paginated=lambda _as_of_date, **_kwargs: (
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
        get_aging_totals=lambda _as_of_date: SimpleNamespace(
            total_clients=0,
            total_current=0,
            total_30_days=0,
            total_60_days=0,
            total_90_plus=0,
            grand_total=0,
        ),
    )
    service.client_record_repo = SimpleNamespace(list_by_ids=lambda _ids: [])

    report = service.generate_aging_report(as_of_date=date(2026, 3, 1))

    assert report["items"] == []
    assert report["total_outstanding"] == 0.0
    assert report["summary"]["total_clients"] == 0


def test_advance_payment_report_uses_client_record_legal_entity_names(test_db):
    service = AdvancePaymentReportService(test_db)
    service.repo = SimpleNamespace(
        get_collections_aggregates=lambda _year, _month: [
            SimpleNamespace(
                client_record_id=7,
                total_expected=Decimal("300.00"),
                total_paid=Decimal("120.00"),
                total_withheld=Decimal("10.00"),
                overdue_count=2,
            )
        ]
    )
    service.client_identity_repo = SimpleNamespace(
        get_display_map=lambda _ids: {
            7: SimpleNamespace(
                client_name="Advance Client",
                office_client_number=101234,
                id_number="123456789",
            )
        }
    )

    report = service.get_collections_report(year=2026, month=3)

    assert report["items"] == [
        {
            "client_record_id": 7,
            "office_client_number": 101234,
            "client_name": "Advance Client",
            "client_id_number": "123456789",
            "total_expected": 300.0,
            "total_paid": 120.0,
            "total_withheld": 10.0,
            "overdue_count": 2,
            "gap": 180.0,
        }
    ]


def test_advance_payment_report_batches_client_name_lookup(test_db, create_client_with_business):
    for _suffix in range(20, 28):
        client, _business = create_client_with_business()
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
