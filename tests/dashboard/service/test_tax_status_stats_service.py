from datetime import date
from types import SimpleNamespace

from app.common.enums import VatType
from app.dashboard.services.dashboard_tax_status_stats_service import TaxStatusStatsService


def _service(test_db, required: int, submitted: int) -> TaxStatusStatsService:
    service = TaxStatusStatsService(test_db)
    service.client_repo = SimpleNamespace(count_active_by_vat_type=lambda _vat_type: required)
    service.vat_repo = SimpleNamespace(
        count_filed_by_period_type=lambda _period, _vat_type: submitted
    )
    return service


def test_vat_status_label_marks_overdue_period(test_db):
    stat = _service(test_db, required=2, submitted=1)._build_stat(
        VatType.MONTHLY,
        "2026-03",
        "מרץ 2026",
        date(2026, 4, 30),
        2,
        1,
        date(2026, 4, 15),
    )

    assert stat["status_label"] == "מועד הגשה עבר"
    assert stat["pending"] == 1


def test_vat_status_label_marks_completed_period(test_db):
    stat = _service(test_db, required=2, submitted=2)._build_stat(
        VatType.MONTHLY,
        "2026-03",
        "מרץ 2026",
        date(2026, 4, 30),
        2,
        2,
        date(2026, 4, 15),
    )

    assert stat["status_label"] == "הושלמה"


def test_advance_dashboard_stats_use_current_periods(test_db):
    service = _service(test_db, required=0, submitted=0)
    calls = []

    def completion(periods):
        calls.extend(periods)
        return {
            ("2026-04", 1): (3, 4),
            ("2026-03", 2): (1, 2),
        }

    service.advance_repo = SimpleNamespace(completion_for_periods=completion)

    stats = service._build_advance_stats(date(2026, 5, 8))

    assert calls == [("2026-04", 1), ("2026-03", 2)]
    assert stats["monthly"]["completion_percent"] == 75
    assert stats["monthly"]["submitted"] == 3
    assert stats["monthly"]["required"] == 4
    assert stats["bimonthly"]["completion_percent"] == 50


def test_advance_dashboard_stats_avoid_division_by_zero(test_db):
    service = _service(test_db, required=0, submitted=0)
    service.advance_repo = SimpleNamespace(
        completion_for_periods=lambda _periods: {("2026-04", 1): (0, 0)}
    )

    stat = service._build_advance_stat("2026-04", "אפריל 2026", 0, 0)

    assert stat["completion_percent"] == 0
    assert stat["pending"] == 0
