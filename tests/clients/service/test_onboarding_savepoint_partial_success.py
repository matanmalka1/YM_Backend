"""
Flow-1 gap: SAVEPOINT partial-success in generate_client_obligations_result.

best_effort=True creates each year's AnnualReport inside an independent SAVEPOINT.
When year 2 fails, only year 2 is rolled back; year 1 persists.
When best_effort=False, any failure propagates out immediately.
"""

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.actions.services.obligation_orchestrator import generate_client_obligations_result
from app.annual_reports.models.annual_report_model import AnnualReport
from app.annual_reports.services.annual_report_create_service import AnnualReportCreateService
from app.common.enums import EntityType, IdNumberType


def _client(client_factory, id_number: str) -> int:
    return client_factory(
        full_name="Savepoint Test Client",
        id_number=id_number,
        entity_type=EntityType.OSEK_MURSHE,
        id_number_type=IdNumberType.INDIVIDUAL,
    ).id


def _fail_on_second_call(original):
    """Return a patched create_report that raises RuntimeError on the 2nd call."""
    call_count = [0]

    def patched(self, client_record_id, tax_year, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("simulated year-2 failure")
        return original(self, client_record_id, tax_year, **kwargs)

    return patched


def test_best_effort_year1_persists_when_year2_fails(test_db, client_factory, actor_user):
    """
    best_effort=True + year-2 failure: year-1 SAVEPOINT is RELEASED before the failure,
    so year-1 AnnualReport survives. result.errors records the failed year.
    """
    client_id = _client(client_factory, "SP-TEST-001")
    # December reference_date → _years_to_generate returns [year, year+1]
    reference_date = date(2025, 12, 31)

    patched = _fail_on_second_call(AnnualReportCreateService.create_report)
    with patch.object(AnnualReportCreateService, "create_report", patched):
        result = generate_client_obligations_result(
            test_db,
            client_id,
            actor_id=actor_user.id,
            entity_type=EntityType.OSEK_MURSHE,
            reference_date=reference_date,
            best_effort=True,
        )

    reports = list(
        test_db.scalars(select(AnnualReport).where(AnnualReport.client_record_id == client_id))
    )
    assert result.reports_created == 1, "year 1 report should have been created"
    assert len(result.errors) == 1, "year 2 failure should be recorded in errors"
    assert "annual_report_creation_failed" in result.errors[0]
    assert len(reports) == 1, "only year 1 report persists; year 2 SAVEPOINT was rolled back"


def test_best_effort_true_continues_after_year2_failure(test_db, client_factory, actor_user):
    """best_effort=True does not raise; result.errors carries the failure record."""
    client_id = _client(client_factory, "SP-TEST-003")
    reference_date = date(2025, 12, 31)

    patched = _fail_on_second_call(AnnualReportCreateService.create_report)
    with patch.object(AnnualReportCreateService, "create_report", patched):
        result = generate_client_obligations_result(
            test_db,
            client_id,
            actor_id=actor_user.id,
            entity_type=EntityType.OSEK_MURSHE,
            reference_date=reference_date,
            best_effort=True,
        )

    assert result is not None, "best_effort=True must not raise"
    assert len(result.errors) == 1


def test_best_effort_false_propagates_exception_on_year2_failure(
    test_db, client_factory, actor_user
):
    """
    best_effort=False: year-2 failure re-raises immediately.
    The caller (get_db / request handler) is responsible for rolling back.
    """
    client_id = _client(client_factory, "SP-TEST-002")
    reference_date = date(2025, 12, 31)

    patched = _fail_on_second_call(AnnualReportCreateService.create_report)
    with patch.object(AnnualReportCreateService, "create_report", patched):
        with pytest.raises(RuntimeError, match="simulated year-2 failure"):
            generate_client_obligations_result(
                test_db,
                client_id,
                actor_id=actor_user.id,
                entity_type=EntityType.OSEK_MURSHE,
                reference_date=reference_date,
                best_effort=False,
            )
