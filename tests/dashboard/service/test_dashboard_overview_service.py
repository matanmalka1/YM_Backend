from sqlalchemy import event

from app.dashboard.services.dashboard_overview_service import DashboardOverviewService
from app.users.models.user import UserRole


def test_secretary_overview_returns_operational_subset(test_db):
    overview = DashboardOverviewService(test_db).get_overview(user_role=UserRole.SECRETARY)

    assert overview["is_empty"] is True
    assert overview["attention"]["items"] == []
    assert overview["open_charges_count"] == 0
    assert overview["open_charges_amount_ils"] is None


def test_advisor_overview_query_count_stays_bounded(test_db):
    # Clean advisor overview currently performs about 15 queries. Allow small growth for
    # setup/dialect differences, but catch N+1 regressions.
    expected_clean_run_queries = 15
    allowed_growth = 2
    statements = []

    def track_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    bind = test_db.get_bind()
    event.listen(bind, "before_cursor_execute", track_query)
    try:
        overview = DashboardOverviewService(test_db).get_overview(user_role=UserRole.ADVISOR)
    finally:
        event.remove(bind, "before_cursor_execute", track_query)

    assert "vat_stats" in overview
    assert "attention" in overview
    assert "recent_activity" in overview
    assert len(statements) <= expected_clean_run_queries + allowed_growth
