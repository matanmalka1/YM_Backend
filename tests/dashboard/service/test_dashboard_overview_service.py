from datetime import date, timedelta

from sqlalchemy import event

from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.dashboard.services.dashboard_overview_service import DashboardOverviewService
from app.users.models.user import UserRole
from tests.helpers.task_helpers import create_business


def test_secretary_overview_shares_attention_but_hides_charge_stats(test_db):
    biz = create_business(test_db)
    test_db.add(
        Charge(
            client_record_id=biz.client_id,
            business_id=biz.id,
            amount=500,
            charge_type=ChargeType.OTHER,
            status=ChargeStatus.ISSUED,
            issued_at=date.today() - timedelta(days=31),
        )
    )
    test_db.commit()

    overview = DashboardOverviewService(test_db).get_overview(user_role=UserRole.SECRETARY)

    # Attention board is shared with secretary — same items as advisor, including charge amounts.
    assert len(overview["attention"]["items"]) > 0
    # The open-charges stat card and recent activity remain advisor-only.
    assert overview["open_charges_count"] == 0
    assert overview["open_charges_amount_ils"] is None
    assert overview["recent_activity"] == []


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
