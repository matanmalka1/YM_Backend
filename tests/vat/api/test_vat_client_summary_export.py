import io
from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest

from app.common.enums import VatType
from app.tax_calendar.services.materialization_service import (
    TaxCalendarMaterializationService,
)
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
from app.vat.services.vat_client_summary_service import get_client_summary
from app.vat.services.vat_export_service import _load as export_load

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _seed_work_items(db, client_record_id: int, created_by: int):
    materializer = TaxCalendarMaterializationService(db)
    feb_entry = materializer.ensure_periodic_entry("vat", "2026-02", 1)
    jan_entry = materializer.ensure_periodic_entry("vat", "2026-01", 1)
    items = [
        VatWorkItem(
            client_record_id=client_record_id,
            created_by=created_by,
            period="2026-02",
            period_type=VatType.MONTHLY,
            status=VatWorkItemStatus.READY_FOR_REVIEW,
            total_output_vat=Decimal("1500.00"),
            total_input_vat=Decimal("500.00"),
            net_vat=Decimal("1000.00"),
            total_output_net=Decimal("0.00"),
            total_input_net=Decimal("0.00"),
            final_vat_amount=None,
            tax_calendar_entry_id=feb_entry.id,
            due_date_original=feb_entry.due_date,
            due_date_effective=feb_entry.due_date,
        ),
        VatWorkItem(
            client_record_id=client_record_id,
            created_by=created_by,
            period="2026-01",
            period_type=VatType.MONTHLY,
            status=VatWorkItemStatus.FILED,
            total_output_vat=Decimal("800.00"),
            total_input_vat=Decimal("200.00"),
            net_vat=Decimal("600.00"),
            total_output_net=Decimal("0.00"),
            total_input_net=Decimal("0.00"),
            final_vat_amount=Decimal("600.00"),
            filed_at=datetime(2026, 2, 15),
            filed_by=created_by,
            tax_calendar_entry_id=jan_entry.id,
            due_date_original=jan_entry.due_date,
            due_date_effective=jan_entry.due_date,
        ),
    ]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


def test_vat_client_summary_returns_periods_and_annual(
    client, test_db, advisor_headers, vat_client, test_user
):
    _seed_work_items(test_db, vat_client.id, test_user.id)

    resp = client.get(f"/api/v1/vat/clients/{vat_client.id}/summary", headers=advisor_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["client_record_id"] == vat_client.id
    assert [row["period"] for row in payload["periods"]] == ["2026-02", "2026-01"]
    assert len(payload["annual"]) == 1
    assert payload["annual"][0]["year"] == 2026
    assert float(payload["annual"][0]["total_output_vat"]) == 2300.0
    assert float(payload["annual"][0]["total_input_vat"]) == 700.0
    assert float(payload["annual"][0]["net_vat"]) == 1600.0
    assert payload["annual"][0]["periods_count"] == 2
    assert payload["annual"][0]["filed_count"] == 1


def test_vat_client_work_items_endpoint(client, test_db, advisor_headers, vat_client, test_user):
    _seed_work_items(test_db, vat_client.id, test_user.id)

    resp = client.get(
        f"/api/v1/vat/clients/{vat_client.id}/work-items",
        headers=advisor_headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert payload["items"][0]["period"] == "2026-02"
    assert payload["items"][1]["period"] == "2026-01"
    assert payload["items"][0]["client_name"] == vat_client.full_name
    assert payload["items"][1]["filed_by_name"] == test_user.full_name


def test_vat_client_export_excel(client, test_db, advisor_headers, vat_client, test_user):
    _seed_work_items(test_db, vat_client.id, test_user.id)

    resp = client.get(
        f"/api/v1/vat/clients/{vat_client.id}/export?format=excel&year=2026",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(EXCEL_MEDIA_TYPE)

    workbook = openpyxl.load_workbook(io.BytesIO(resp.content))
    sheet = workbook.active
    assert sheet["A1"].value is not None
    assert sheet["A4"].value == "2026-02"


def test_vat_client_export_pdf_service_error_returns_500(
    client, advisor_headers, vat_client, monkeypatch
):
    monkeypatch.setattr(
        "app.vat.api.routes_client_summary.export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fail")),
    )

    with pytest.raises(RuntimeError, match="fail"):
        client.get(
            f"/api/v1/vat/clients/{vat_client.id}/export?format=pdf&year=2026",
            headers=advisor_headers,
        )


def test_vat_client_export_import_error_returns_detail(
    client, advisor_headers, vat_client, monkeypatch
):
    monkeypatch.setattr(
        "app.vat.api.routes_client_summary.export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ImportError("openpyxl missing")),
    )

    with pytest.raises(ImportError, match="openpyxl missing"):
        client.get(
            f"/api/v1/vat/clients/{vat_client.id}/export?format=excel&year=2026",
            headers=advisor_headers,
        )


def test_client_summary_service_uses_snapshot_deadline(test_db, vat_client, test_user):
    _seed_work_items(test_db, vat_client.id, test_user.id)
    materializer = TaxCalendarMaterializationService(test_db)
    jan_entry = materializer.ensure_periodic_entry("vat", "2026-01", 1)

    result = get_client_summary(test_db, client_record_id=vat_client.id)

    jan_row = next(p for p in result.periods if p.period == "2026-01")
    assert jan_row.statutory_deadline == jan_entry.due_date, (
        f"expected registry-shifted date {jan_entry.due_date!r} from snapshot"
    )
    assert jan_row.statutory_deadline is not None
    assert jan_row.statutory_deadline != date(2026, 2, 15)


def test_export_service_uses_snapshot_deadline(test_db, vat_client, test_user):
    _seed_work_items(test_db, vat_client.id, test_user.id)
    materializer = TaxCalendarMaterializationService(test_db)
    jan_entry = materializer.ensure_periodic_entry("vat", "2026-01", 1)

    _, periods = export_load(test_db, vat_client.id, 2026)

    jan_row = next(p for p in periods if p.period == "2026-01")
    assert jan_row.statutory_deadline == jan_entry.due_date, (
        f"expected registry-shifted date {jan_entry.due_date!r} from snapshot"
    )
    assert jan_row.statutory_deadline != date(2026, 2, 15)
