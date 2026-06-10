from datetime import UTC, datetime

from app.common.enums import VatType
from app.vat.models.vat_enums import VatWorkItemStatus
from tests.helpers.tax_calendar_links import create_linked_vat_work_item
from tests.reports.api.test_reports_additional_endpoints import (
    _create_client_and_business,
)


def test_vat_compliance_groups_same_client_by_period_type(
    client,
    test_db,
    advisor_headers,
    test_user,
):
    crm_client, _ = _create_client_and_business(test_db, "VAT-GROUP")
    now = datetime.now(UTC)
    item1 = create_linked_vat_work_item(
        test_db,
        period_type=VatType.MONTHLY,
        client_record_id=crm_client.id,
        created_by=test_user.id,
        period="2026-01",
        status=VatWorkItemStatus.FILED,
    )
    item1.filed_at = datetime(2026, 2, 10, 9, 0, 0)
    item1.updated_at = now
    item2 = create_linked_vat_work_item(
        test_db,
        period_type=VatType.BIMONTHLY,
        client_record_id=crm_client.id,
        created_by=test_user.id,
        period="2026-03",
        status=VatWorkItemStatus.PENDING_MATERIALS,
    )
    item2.updated_at = now
    test_db.commit()

    response = client.get(
        "/api/v1/reports/vat-compliance?year=2026",
        headers=advisor_headers,
    )

    assert response.status_code == 200
    items = sorted(response.json()["items"], key=lambda item: item["period_type"])
    assert [item["period_type"] for item in items] == ["bimonthly", "monthly"]
    assert all(item["year"] == 2026 for item in items)
    assert all(item["grouping_key"] for item in items)
