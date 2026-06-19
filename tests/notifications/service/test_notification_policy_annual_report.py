"""Tests: annual report domain policies in NotificationPolicyService."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.notifications.models.notification import NotificationStatus, NotificationTrigger
from app.notifications.services.notification_policy_service import (
    ANNUAL_REMINDER_COOLDOWN_DAYS,
    NotificationPolicyService,
)


def _make_client(client_record_id: int = 10):
    from app.clients.client_enums import ClientStatus

    return SimpleNamespace(id=client_record_id, status=ClientStatus.ACTIVE)


def _make_report(status: AnnualReportStatus, report_id: int = 1):
    return SimpleNamespace(id=report_id, status=status, tax_year=2025, client_record_id=10)


def _make_last_notification(days_ago: int, status: NotificationStatus = NotificationStatus.SENT):
    return SimpleNamespace(
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
        status=status,
    )


def _db(report, last_notification=None):
    """
    Build a fake db object that satisfies both db.get(Model, pk) and the lazy import of
    NotificationRepository inside notification_policy_service.

    The policy uses:
        from app.notifications.repositories.notification_repository import NotificationRepository
        repo = NotificationRepository(db)
        last = repo.get_last_for_annual_report_trigger(...)

    We patch the real NotificationRepository class-level to return our fake repo via the
    constructor by subclassing it and overriding __init__ and get_last_for_annual_report_trigger.
    """
    from app.notifications.repositories import notification_repository as _nr_module

    original_class = _nr_module.NotificationRepository

    class FakeRepo:
        def __init__(self, _db):
            pass

        def get_last_for_annual_report_trigger(self, *args):
            return last_notification

    _nr_module.NotificationRepository = FakeRepo  # type: ignore[assignment]

    class DB:
        def get(self, model, _pk):
            return report

    try:
        return DB()
    finally:
        _nr_module.NotificationRepository = original_class  # type: ignore[assignment]


class _FakeDB:
    """Fake db that returns a given report and patches NotificationRepository in the policy module."""

    def __init__(self, report, last_notification=None):
        self._report = report
        self._last_notification = last_notification
        self._original = None

    def __enter__(self):
        from app.notifications.repositories import notification_repository as _nr_module

        self._original = _nr_module.NotificationRepository
        last = self._last_notification

        class FakeRepo:
            def __init__(self, _db):
                pass

            def get_last_for_annual_report_trigger(self, *args):
                return last

        _nr_module.NotificationRepository = FakeRepo  # type: ignore[assignment]
        return self

    def __exit__(self, *_):
        from app.notifications.repositories import notification_repository as _nr_module

        _nr_module.NotificationRepository = self._original  # type: ignore[assignment]

    def get(self, model, _pk):
        return self._report


# ── ANNUAL_REPORT_CLIENT_REMINDER ─────────────────────────────────────────────


def test_annual_report_client_reminder_blocked_when_wrong_status():
    report = _make_report(AnnualReportStatus.NOT_STARTED)
    with _FakeDB(report) as db:
        policy = NotificationPolicyService()
        result = policy.can_send(
            _make_client(),
            NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
            db=db,
            annual_report_id=1,
        )
    assert result.blocked is True
    assert "ממתין לאישור לקוח" in result.reason


def test_annual_report_client_reminder_allowed_when_pending_client():
    report = _make_report(AnnualReportStatus.PENDING_CLIENT)
    with _FakeDB(report, last_notification=None) as db:
        policy = NotificationPolicyService()
        result = policy.can_send(
            _make_client(),
            NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
            db=db,
            annual_report_id=1,
        )
    assert result.blocked is False


def test_annual_report_client_reminder_cooldown_blocks_resend_within_2_days():
    report = _make_report(AnnualReportStatus.PENDING_CLIENT)
    last = _make_last_notification(days_ago=0, status=NotificationStatus.SENT)
    with _FakeDB(report, last_notification=last) as db:
        policy = NotificationPolicyService()
        result = policy.can_send(
            _make_client(),
            NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
            db=db,
            annual_report_id=1,
        )
    assert result.blocked is True
    assert str(ANNUAL_REMINDER_COOLDOWN_DAYS) in result.reason


def test_annual_report_client_reminder_cooldown_allows_after_2_days():
    report = _make_report(AnnualReportStatus.PENDING_CLIENT)
    last = _make_last_notification(days_ago=ANNUAL_REMINDER_COOLDOWN_DAYS + 1)
    with _FakeDB(report, last_notification=last) as db:
        policy = NotificationPolicyService()
        result = policy.can_send(
            _make_client(),
            NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
            db=db,
            annual_report_id=1,
        )
    assert result.blocked is False


def test_annual_report_client_reminder_skipped_notifications_dont_trigger_cooldown():
    """A SKIPPED last notification should not count for cooldown."""
    report = _make_report(AnnualReportStatus.PENDING_CLIENT)
    last = _make_last_notification(days_ago=0, status=NotificationStatus.SKIPPED)
    with _FakeDB(report, last_notification=last) as db:
        policy = NotificationPolicyService()
        result = policy.can_send(
            _make_client(),
            NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
            db=db,
            annual_report_id=1,
        )
    assert result.blocked is False


def test_annual_report_client_reminder_blocked_when_no_db():
    """Without db or annual_report_id, policy blocks — entity context is required."""
    policy = NotificationPolicyService()
    result = policy.can_send(
        _make_client(),
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
    )
    assert result.blocked is True
    assert "מזהה דוח שנתי" in result.reason


def test_annual_report_client_reminder_blocked_when_wrong_client():
    """Report belongs to different client — ownership check blocks."""
    report = _make_report(AnnualReportStatus.PENDING_CLIENT, report_id=1)
    # client_record_id=10 in report, but caller is client 99
    with _FakeDB(report, last_notification=None) as db:
        policy = NotificationPolicyService()
        result = policy.can_send(
            _make_client(client_record_id=99),
            NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
            db=db,
            annual_report_id=1,
        )
    assert result.blocked is True


# ── ANNUAL_REPORT_DOCUMENTS_REQUEST ───────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [
        AnnualReportStatus.NOT_STARTED,
        AnnualReportStatus.COLLECTING_DOCS,
        AnnualReportStatus.IN_PREPARATION,
    ],
)
def test_annual_report_documents_request_allowed_for_valid_statuses(status):
    report = _make_report(status)
    db = SimpleNamespace(get=lambda model, _pk: report)
    policy = NotificationPolicyService()
    result = policy.can_send(
        _make_client(),
        NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
        db=db,
        annual_report_id=1,
    )
    assert result.blocked is False


@pytest.mark.parametrize(
    "status",
    [
        AnnualReportStatus.PENDING_CLIENT,
        AnnualReportStatus.SUBMITTED,
        AnnualReportStatus.CLOSED,
        AnnualReportStatus.CANCELED,
    ],
)
def test_annual_report_documents_request_blocked_for_invalid_statuses(status):
    report = _make_report(status)
    db = SimpleNamespace(get=lambda model, _pk: report)
    policy = NotificationPolicyService()
    result = policy.can_send(
        _make_client(),
        NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
        db=db,
        annual_report_id=1,
    )
    assert result.blocked is True


def test_annual_report_documents_request_blocked_when_report_not_found():
    db = SimpleNamespace(get=lambda model, _pk: None)
    policy = NotificationPolicyService()
    result = policy.can_send(
        _make_client(),
        NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
        db=db,
        annual_report_id=999,
    )
    assert result.blocked is True


def test_annual_report_documents_request_blocked_when_no_annual_report_id():
    """Missing annual_report_id must block even when db is present."""
    db = SimpleNamespace(get=lambda model, _pk: None)
    policy = NotificationPolicyService()
    result = policy.can_send(
        _make_client(),
        NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
        db=db,
    )
    assert result.blocked is True
    assert "מזהה דוח שנתי" in result.reason
