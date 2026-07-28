from datetime import date
from decimal import Decimal

from app.annual_reports.models.annual_report_enums import (
    ClientAnnualFilingType,
    FilingDeadlineType,
    PrimaryAnnualReportForm,
)
from app.annual_reports.models.annual_report_model import AnnualReport
from app.common.enums import ObligationStatus
from tests.helpers.identity import seed_business, seed_client_identity
from tests.helpers.tax_calendar_links import create_tax_calendar_entry_for_annual


def _seed_businesses_and_reports(db, creator_id: int, tax_year: int):
    """Create businesses and reports across submission stages for dashboard widget."""
    clients = [
        seed_client_identity(db, full_name="Submitted Corp", id_number="DASH-001"),
        seed_client_identity(db, full_name="In Prep", id_number="DASH-002"),
        seed_client_identity(db, full_name="Collecting Docs", id_number="DASH-003"),
        seed_client_identity(db, full_name="Not Started", id_number="DASH-004"),
    ]

    businesses = [
        seed_business(
            db,
            legal_entity_id=clients[0].legal_entity_id,
            business_name="Submitted Corp Biz",
            opened_at=date.today(),
        ),
        seed_business(
            db,
            legal_entity_id=clients[1].legal_entity_id,
            business_name="In Prep Biz",
            opened_at=date.today(),
        ),
        seed_business(
            db,
            legal_entity_id=clients[2].legal_entity_id,
            business_name="Collecting Docs Biz",
            opened_at=date.today(),
        ),
        seed_business(
            db,
            legal_entity_id=clients[3].legal_entity_id,
            business_name="Not Started Biz",
            opened_at=date.today(),
        ),
    ]
    db.commit()
    for business in businesses:
        db.refresh(business)
    for business, crm_client in zip(businesses, clients, strict=False):
        business.client_id = crm_client.id
    entry = create_tax_calendar_entry_for_annual(db, tax_year)

    reports = [
        AnnualReport(
            client_record_id=clients[0].id,
            created_by=creator_id,
            tax_year=tax_year,
            client_type=ClientAnnualFilingType.CORPORATION,
            form_type=PrimaryAnnualReportForm.FORM_1214,
            status=ObligationStatus.SUBMITTED,
            deadline_type=FilingDeadlineType.STANDARD,
            refund_due=Decimal("100.00"),
            tax_due=Decimal("50.00"),
            tax_calendar_entry_id=entry.id,
        ),
        AnnualReport(
            client_record_id=clients[1].id,
            created_by=creator_id,
            tax_year=tax_year,
            client_type=ClientAnnualFilingType.INDIVIDUAL,
            form_type=PrimaryAnnualReportForm.FORM_1301,
            status=ObligationStatus.IN_PROGRESS,
            deadline_type=FilingDeadlineType.STANDARD,
            refund_due=Decimal("20.00"),
            tax_due=Decimal("75.00"),
            tax_calendar_entry_id=entry.id,
        ),
        AnnualReport(
            client_record_id=clients[2].id,
            created_by=creator_id,
            tax_year=tax_year,
            client_type=ClientAnnualFilingType.SELF_EMPLOYED,
            form_type=PrimaryAnnualReportForm.FORM_1301,
            status=ObligationStatus.AWAITING_INPUT,
            deadline_type=FilingDeadlineType.STANDARD,
            refund_due=Decimal("0.00"),
            tax_due=Decimal("0.00"),
            tax_calendar_entry_id=entry.id,
        ),
        AnnualReport(
            client_record_id=clients[3].id,
            created_by=creator_id,
            tax_year=tax_year,
            client_type=ClientAnnualFilingType.INDIVIDUAL,
            form_type=PrimaryAnnualReportForm.FORM_1301,
            status=ObligationStatus.AWAITING_INPUT,
            deadline_type=FilingDeadlineType.STANDARD,
            tax_calendar_entry_id=entry.id,
        ),
    ]
    db.add_all(reports)
    db.commit()


def test_tax_submission_widget_counts(client, test_db, advisor_headers, test_user):
    tax_year = 2099
    _seed_businesses_and_reports(test_db, creator_id=test_user.id, tax_year=tax_year)

    resp = client.get(
        f"/api/v1/dashboard/tax-submissions?tax_year={tax_year}",
        headers=advisor_headers,
    )

    assert resp.status_code == 200
    data = resp.json()

    assert data["tax_year"] == tax_year
    assert data["total_clients"] >= 4
    assert data["reports_submitted"] == 1
    assert data["reports_in_progress"] == 1  # IN_PREPARATION
    # total − submitted − in_progress − material_collection
    assert data["reports_not_started"] == data["total_clients"] - 3
    assert data["submission_percentage"] == round((1 / data["total_clients"]) * 100, 1)

    assert Decimal(str(data["total_refund_due"])) == Decimal("120.00")
    assert Decimal(str(data["total_tax_due"])) == Decimal("125.00")
