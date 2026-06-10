from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.businesses.models.business import Business
from app.clients.models.client_record import ClientRecord
from app.legal_entities.models.legal_entity import LegalEntity
from app.common.enums import IdNumberType, VatType
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from app.vat.services.vat_export_pdf import export_vat_to_pdf
from app.vat.services.vat_export_service import export_to_pdf
from app.vat.services.vat_report_service import VatReportService
from tests.helpers.tax_calendar_links import create_linked_vat_work_item


def _user(test_db) -> User:
    user = User(
        full_name="VAT Export User",
        email="vat.export.user@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def _business(test_db) -> tuple[Business, int]:
    legal_entity = LegalEntity(
        official_name="VAT Export Client",
        id_number="VEP001",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    test_db.add(legal_entity)
    test_db.commit()
    test_db.refresh(legal_entity)

    client_record = ClientRecord(legal_entity_id=legal_entity.id)
    test_db.add(client_record)
    test_db.commit()
    test_db.refresh(client_record)

    business = Business(
        legal_entity_id=legal_entity.id,
        business_name=legal_entity.official_name,
        opened_at=date(2026, 1, 1),
    )
    test_db.add(business)
    test_db.commit()
    test_db.refresh(business)
    return business, client_record.id


def test_export_to_pdf_filters_periods_by_year_and_delegates(test_db, monkeypatch):
    user = _user(test_db)
    _, client_record_id = _business(test_db)
    service = VatReportService(test_db)
    item_2026 = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record_id,
        period="2026-01",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    item_2025 = create_linked_vat_work_item(
        test_db,
        repo=service.work_item_repo,
        client_record_id=client_record_id,
        period="2025-12",
        period_type=VatType.MONTHLY,
        created_by=user.id,
    )
    service.work_item_repo.update_vat_totals(item_2026.id, 170.0, 20.0, 1000.0, 200.0)
    service.work_item_repo.update_vat_totals(item_2025.id, 85.0, 10.0, 500.0, 100.0)

    captured = {}

    def _fake_export(client_name, client_id, year, periods, export_dir):
        captured["client_name"] = client_name
        captured["client_id"] = client_id
        captured["year"] = year
        captured["periods"] = periods
        captured["export_dir"] = export_dir
        return {
            "format": "pdf",
            "filepath": "/tmp/fake.pdf",
            "filename": "fake.pdf",
            "generated_at": datetime.now(UTC),
        }

    monkeypatch.setattr(
        "app.vat.services.vat_export_service.export_vat_to_pdf",
        _fake_export,
    )

    payload = export_to_pdf(test_db, client_record_id, 2026)
    assert payload["format"] == "pdf"
    assert captured["client_id"] == client_record_id
    assert captured["year"] == 2026
    assert len(captured["periods"]) == 1
    assert captured["periods"][0].period == "2026-01"


def test_export_vat_to_pdf_generates_file_when_reportlab_available_or_raises():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError):
            export_vat_to_pdf(
                client_name="Client",
                client_record_id=1,
                year=2026,
                periods=[],
                export_dir="/tmp",
            )
        return

    from app.vat.models.vat_enums import VatWorkItemStatus
    from app.vat.schemas.vat_client_summary_schema import VatPeriodRow

    period = VatPeriodRow(
        period="2026-01",
        period_type="monthly",
        status=VatWorkItemStatus.FILED,
        total_output_vat=Decimal("170.00"),
        total_input_vat=Decimal("20.00"),
        net_vat=Decimal("150.00"),
        final_vat_amount=Decimal("150.00"),
        filed_at=datetime.now(UTC) - timedelta(days=1),
        submission_deadline=None,
        statutory_deadline=None,
        extended_deadline=None,
        days_until_deadline=None,
        is_overdue=None,
    )

    payload = export_vat_to_pdf(
        client_name="Client",
        client_record_id=1,
        year=2026,
        periods=[period],
        export_dir="/tmp",
    )
    assert payload["format"] == "pdf"
    assert Path(payload["filepath"]).exists()
