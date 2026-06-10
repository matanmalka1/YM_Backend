from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from tax_rules import get_financial

from app.advance_payments.models.advance_payment import AdvancePayment
from app.annual_reports.models import AnnualReport
from app.binders.models.binder import Binder
from app.clients.services.create_client_service import create_client_identity_only
from app.clients.services.impact_preview_service import compute_creation_impact
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.tax_calendar.services.bootstrap import bootstrap_tax_calendar
from app.vat.models.vat_work_item import VatWorkItem


def test_preview_impact_returns_backend_vat_exempt_ceiling(client, advisor_headers):
    response = client.post(
        "/api/v1/clients/preview-impact",
        headers=advisor_headers,
        json={"client": {"entity_type": "osek_patur"}},
    )

    assert response.status_code == 200
    year = date.today().year
    expected = Decimal(str(get_financial(year, "osek_patur_ceiling_ils").value))
    expected = str(expected.quantize(Decimal("0.01")))
    assert response.json()["vat_exempt_ceiling"] == expected


def test_preview_impact_materializes_missing_tax_calendar(client, advisor_headers):
    response = client.post(
        "/api/v1/clients/preview-impact",
        headers=advisor_headers,
        json={
            "client": {
                "entity_type": "osek_murshe",
                "vat_reporting_frequency": "monthly",
                "advance_payment_frequency": "monthly",
            }
        },
    )

    assert response.status_code == 200
    counts = {item["label"]: item["count"] for item in response.json()["items"]}
    assert counts["קלסר פעיל"] == 1
    assert counts['דוחות מע"מ'] > 0
    assert counts["רשומות מקדמות"] > 0


def test_preview_impact_matches_actual_future_generation(test_db):
    reference_date = date(2026, 4, 30)
    bootstrap_tax_calendar(test_db, start_year=2026, end_year=2027)

    preview = compute_creation_impact(
        test_db,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        reference_date=reference_date,
    )
    counts = {item.label: item.count for item in preview.items}

    assert 'מועדי מע"מ' not in counts
    assert "מועדי מקדמות" not in counts
    assert "מועד הגשת דוח שנתי" not in counts

    client_record = create_client_identity_only(
        test_db,
        full_name="Preview Match Client",
        id_number="123456780",
        id_number_type=IdNumberType.INDIVIDUAL,
        entity_type=EntityType.OSEK_MURSHE,
        vat_reporting_frequency=VatType.MONTHLY,
        advance_payment_frequency=AdvancePaymentFrequency.MONTHLY,
        advance_rate=Decimal("5.0"),
        actor_id=1,
        reference_date=reference_date,
    )
    vat_work_items_count = test_db.scalar(
        select(func.count())
        .select_from(VatWorkItem)
        .filter(VatWorkItem.client_record_id == client_record.id)
    )
    advance_payments_count = test_db.scalar(
        select(func.count())
        .select_from(AdvancePayment)
        .filter(AdvancePayment.client_record_id == client_record.id)
    )
    reports_count = test_db.scalar(
        select(func.count())
        .select_from(AnnualReport)
        .filter(AnnualReport.client_record_id == client_record.id)
    )
    binders_count = test_db.scalar(
        select(func.count()).select_from(Binder).filter(Binder.client_record_id == client_record.id)
    )

    assert binders_count == 1
    assert vat_work_items_count == counts.get('דוחות מע"מ', 0)
    assert advance_payments_count == counts.get("רשומות מקדמות", 0)
    assert reports_count == counts.get("דוח שנתי", 0)
