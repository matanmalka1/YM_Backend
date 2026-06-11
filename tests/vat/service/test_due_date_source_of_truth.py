"""Regression tests: due-date source-of-truth is TaxCalendarEntry, not hardcoded day constants."""

from datetime import date

from app.common.enums import DeadlineRuleType, ObligationType, VatType
from app.vat.api.serializers import serialize_enriched_work_item
from app.vat.repositories.vat_work_item_repository import VatWorkItemRepository
from app.vat.services.intake import create_work_item
from tests.tax_calendar.service.linking_helpers import make_entry, vat_client


def test_serializer_prefers_snapshot_over_computed_deadline(test_db):
    """When due_date_effective is set, submission_deadline must come from snapshot, not period+15."""
    entry = make_entry(
        test_db,
        obligation_type=ObligationType.VAT,
        rule_type=DeadlineRuleType.VAT_MONTHLY,
        period="2026-01",
        months=1,
        tax_year=2026,
    )
    # Override entry's due_date to 16th (holiday-shifted)
    entry.due_date = date(2026, 2, 16)
    test_db.flush()

    client = vat_client(test_db, VatType.MONTHLY)
    item = create_work_item(
        VatWorkItemRepository(test_db),
        test_db,
        client_record_id=client.id,
        period="2026-01",
        created_by=1,
    )

    assert item.due_date_effective == date(2026, 2, 16), "snapshot must use entry.due_date=16th"

    result = serialize_enriched_work_item(
        item,
        office_client_number_map={},
        name_map={},
        id_number_map={},
        status_map={},
        user_map={},
    )

    assert result.submission_deadline == date(2026, 2, 16), (
        f"expected 2026-02-16 from snapshot, got {result.submission_deadline} (hardcoded 15th would be wrong)"
    )
    assert result.statutory_deadline == date(2026, 2, 16)
    # extended_deadline == effective: snapshot path does not add +4
    assert result.extended_deadline == date(2026, 2, 16)
