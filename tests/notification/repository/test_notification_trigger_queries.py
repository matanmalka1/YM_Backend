from datetime import date, timedelta

from app.annual_reports.services.annual_report_service import AnnualReportService
from app.binders.repositories.binder_repository import BinderRepository
from app.notification.models.notification import (
    NotificationChannel,
    NotificationTrigger,
)
from app.notification.repositories.notification_repository import NotificationRepository
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from app.utils.time_utils import utcnow
from tests.helpers.identity import seed_client_identity


def _user(test_db):
    user = User(
        full_name="Notification Trigger User",
        email="notification.trigger@example.com",
        password_hash=AuthService.hash_password("pass"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.flush()
    return user


def _create_notification(repo, client_id, trigger, **kwargs):
    return repo.create(
        client_record_id=client_id,
        trigger=trigger,
        channel=NotificationChannel.EMAIL,
        recipient="client@example.com",
        content_snapshot="content",
        **kwargs,
    )


def test_get_last_for_binder_trigger_returns_newest_matching_notification(test_db):
    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="Trigger Binder", id_number="NTB001")
    binder = BinderRepository(test_db).create(client.id, "NTB-1", date(2026, 1, 1), user.id)
    repo = NotificationRepository(test_db)
    older = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_READY_FOR_HANDOVER, binder_id=binder.id
    )
    newer = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_READY_FOR_HANDOVER, binder_id=binder.id
    )
    other = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_MISSING_DOCUMENTS, binder_id=binder.id
    )
    older.created_at = utcnow() - timedelta(days=2)
    newer.created_at = utcnow() - timedelta(days=1)
    other.created_at = utcnow()
    test_db.commit()

    assert (
        repo.get_last_for_binder_trigger(
            binder.id, NotificationTrigger.BINDER_READY_FOR_HANDOVER
        ).id
        == newer.id
    )


def test_latest_by_binder_ids_returns_newest_per_binder(test_db):
    user = _user(test_db)
    client = seed_client_identity(test_db, full_name="Trigger Binder Batch", id_number="NTB002")
    repo = NotificationRepository(test_db)
    binder_a = BinderRepository(test_db).create(client.id, "NTB-2", date(2026, 1, 1), user.id)
    binder_b = BinderRepository(test_db).create(client.id, "NTB-3", date(2026, 1, 1), user.id)

    older_a = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_READY_FOR_HANDOVER, binder_id=binder_a.id
    )
    newer_a = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_READY_FOR_HANDOVER, binder_id=binder_a.id
    )
    newer_b = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_READY_FOR_HANDOVER, binder_id=binder_b.id
    )
    ignored = _create_notification(
        repo, client.id, NotificationTrigger.BINDER_MISSING_DOCUMENTS, binder_id=binder_b.id
    )
    older_a.created_at = utcnow() - timedelta(days=3)
    newer_a.created_at = utcnow() - timedelta(days=1)
    newer_b.created_at = utcnow() - timedelta(days=2)
    ignored.created_at = utcnow()
    test_db.commit()

    result = repo.latest_by_binder_ids(
        [binder_a.id, binder_b.id],
        NotificationTrigger.BINDER_READY_FOR_HANDOVER,
    )

    assert result == {binder_a.id: newer_a, binder_b.id: newer_b}


def test_get_last_for_annual_report_trigger_returns_newest_matching_notification(
    test_db,
):
    client = seed_client_identity(test_db, full_name="Trigger Annual", id_number="NTA001")
    report = AnnualReportService(test_db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="individual",
        created_by=1,
        created_by_name="Tester",
    )
    repo = NotificationRepository(test_db)
    older = _create_notification(
        repo,
        client.id,
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
        annual_report_id=report.id,
    )
    newer = _create_notification(
        repo,
        client.id,
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
        annual_report_id=report.id,
    )
    older.created_at = utcnow() - timedelta(days=2)
    newer.created_at = utcnow() - timedelta(days=1)
    test_db.commit()

    result = repo.get_last_for_annual_report_trigger(
        report.id,
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
    )
    assert result.id == newer.id


def test_latest_by_annual_report_ids_returns_newest_per_report(test_db):
    client = seed_client_identity(test_db, full_name="Trigger Annual Batch", id_number="NTA002")
    report_a = AnnualReportService(test_db).create_report(
        client_record_id=client.id,
        tax_year=2026,
        client_type="individual",
        created_by=1,
        created_by_name="Tester",
    )
    report_b = AnnualReportService(test_db).create_report(
        client_record_id=client.id,
        tax_year=2027,
        client_type="individual",
        created_by=1,
        created_by_name="Tester",
    )
    repo = NotificationRepository(test_db)
    older_a = _create_notification(
        repo,
        client.id,
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
        annual_report_id=report_a.id,
    )
    newer_a = _create_notification(
        repo,
        client.id,
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
        annual_report_id=report_a.id,
    )
    newer_b = _create_notification(
        repo,
        client.id,
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
        annual_report_id=report_b.id,
    )
    older_a.created_at = utcnow() - timedelta(days=3)
    newer_a.created_at = utcnow() - timedelta(days=1)
    newer_b.created_at = utcnow() - timedelta(days=2)
    test_db.commit()

    result = repo.latest_by_annual_report_ids(
        [report_a.id, report_b.id],
        NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
    )

    assert result == {report_a.id: newer_a, report_b.id: newer_b}
