"""Tests: NotificationSendService trigger validation and idempotency."""

import pytest
from sqlalchemy import func, select

from app.annual_reports.models.annual_report_enums import AnnualReportStatus
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.audit.audit_constants import ACTION_NOTIFICATION_SENT, ENTITY_NOTIFICATION
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.core.exceptions import AppError
from app.notifications.models.notification import Notification, NotificationTrigger
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import NotificationSendRequest
from app.notifications.services.notification_send_service import NotificationSendService
from tests.helpers.identity import seed_client_identity


def _make_request(trigger: str, entity_id: int | None = None, business_id: int | None = None):
    from app.notifications.schemas.notification_schemas import NotificationPreviewRequest

    return NotificationPreviewRequest(
        client_record_id=1,
        trigger=trigger,  # type: ignore[arg-type]
        entity_id=entity_id,
        business_id=business_id,
    )


def _make_send_request(trigger: str, entity_id: int | None = None, business_id: int | None = None):
    from app.notifications.schemas.notification_schemas import NotificationSendRequest

    return NotificationSendRequest(
        client_record_id=1,
        trigger=trigger,  # type: ignore[arg-type]
        overrides={"subject": "נושא", "body": "גוף ההודעה"},
        entity_id=entity_id,
        business_id=business_id,
    )


class TestPreviewTriggerValidation:
    def test_preview_rejects_binder_ready_for_handover(self, test_db):
        svc = NotificationSendService(test_db)
        req = _make_request("binder_ready_for_handover")
        with pytest.raises(AppError) as exc:
            svc.preview(req, triggered_by=1)
        assert exc.value.code == "NOTIFICATION.AUTO_ONLY_TRIGGER"

    @pytest.mark.parametrize(
        "trigger",
        ["annual_report_client_reminder", "annual_report_documents_request"],
    )
    def test_preview_rejects_annual_trigger_without_entity_id(self, test_db, trigger):
        svc = NotificationSendService(test_db)
        req = _make_request(trigger, entity_id=None)
        with pytest.raises(AppError) as exc:
            svc.preview(req, triggered_by=1)
        assert exc.value.code == "NOTIFICATION.MISSING_ENTITY_ID"

    def test_preview_with_annual_entity_id_reaches_client_lookup(self, test_db):
        svc = NotificationSendService(test_db)
        req = _make_request("annual_report_client_reminder", entity_id=42)

        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            svc.preview(req, triggered_by=1)


class TestSendTriggerValidation:
    def test_send_rejects_binder_ready_for_handover(self, test_db):
        svc = NotificationSendService(test_db)
        req = _make_send_request("binder_ready_for_handover")
        with pytest.raises(AppError) as exc:
            svc.send(req, triggered_by=1, idempotency_key="00000000-0000-4000-8000-000000000001")
        assert exc.value.code == "NOTIFICATION.AUTO_ONLY_TRIGGER"

    @pytest.mark.parametrize(
        ("trigger", "idempotency_key"),
        [
            ("annual_report_client_reminder", "00000000-0000-4000-8000-000000000002"),
            ("annual_report_documents_request", "00000000-0000-4000-8000-000000000003"),
        ],
    )
    def test_send_rejects_annual_trigger_without_entity_id(
        self,
        test_db,
        trigger,
        idempotency_key,
    ):
        svc = NotificationSendService(test_db)
        req = _make_send_request(trigger, entity_id=None)
        with pytest.raises(AppError) as exc:
            svc.send(req, triggered_by=1, idempotency_key=idempotency_key)
        assert exc.value.code == "NOTIFICATION.MISSING_ENTITY_ID"


def test_system_send_can_retry_failed_delivery_without_duplicate_success(test_db, monkeypatch):
    client = seed_client_identity(
        test_db,
        full_name="Reminder Notification Client",
        id_number="REM-NOTIFICATION-001",
        email="reminder-notification@test.com",
    )
    service = NotificationSendService(test_db)
    outcomes = iter([(False, "temporary failure"), (True, None)])
    delivery_calls = 0

    def _deliver(**_kwargs):
        nonlocal delivery_calls
        delivery_calls += 1
        return next(outcomes)

    monkeypatch.setattr(service._delivery, "send", _deliver)
    request = NotificationSendRequest(
        client_record_id=client.id,
        trigger=NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        overrides={"subject": "Reminder", "body": "Please respond"},
    )
    key = "reminder:123:notification"

    first = service.send(
        request,
        triggered_by=None,
        idempotency_key=key,
        actor_name="מערכת",
        retry_failed=True,
    )
    second = service.send(
        request,
        triggered_by=None,
        idempotency_key=key,
        actor_name="מערכת",
        retry_failed=True,
    )
    third = service.send(
        request,
        triggered_by=None,
        idempotency_key=key,
        actor_name="מערכת",
        retry_failed=True,
    )

    assert first.status == "failed"
    assert second.status == "sent"
    assert third.status == "sent"
    assert third.notification_id == second.notification_id
    assert delivery_calls == 2
    assert (
        test_db.scalar(
            select(func.count(Notification.id)).where(Notification.idempotency_key == key)
        )
        == 2
    )

    audit = test_db.scalars(
        select(EntityAuditLog).where(
            EntityAuditLog.entity_type == ENTITY_NOTIFICATION,
            EntityAuditLog.entity_id == second.notification_id,
            EntityAuditLog.action == ACTION_NOTIFICATION_SENT,
        )
    ).one()
    assert audit.actor_type == "system"
    assert audit.actor_display_name == "מערכת"


class TestAnnualReportSendIntegration:
    """Integration tests: annual send path saves annual_report_id and cooldown works."""

    def _send(
        self,
        db,
        client_id: int,
        report_id: int,
        user_id: int,
        idempotency_key: str = "00000000-0000-4000-8000-000000000100",
    ) -> object:
        svc = NotificationSendService(db)
        req = NotificationSendRequest(
            client_record_id=client_id,
            trigger="annual_report_client_reminder",  # type: ignore[arg-type]
            overrides={"subject": "תזכורת לאישור הדוח השנתי", "body": "אנא אשר את הדוח השנתי"},
            entity_id=report_id,
        )
        return svc.send(
            req,
            triggered_by=user_id,
            idempotency_key=idempotency_key,
        )

    def test_annual_send_saves_annual_report_id_on_record(self, test_db, test_user):
        client = seed_client_identity(
            test_db,
            full_name="Annual Integration Client",
            id_number="AIC-001",
            email="annual-int@test.com",
        )
        svc = AnnualReportService(test_db)
        report = svc.create_report(
            client_record_id=client.id,
            tax_year=2025,
            client_type="individual",
            created_by=test_user.id,
            created_by_name=test_user.full_name,
        )
        svc.repo.update(report.id, status=AnnualReportStatus.PENDING_CLIENT)

        result = self._send(test_db, client.id, report.id, test_user.id)

        assert result.status in ("sent", "skipped")
        assert result.notification_id is not None

        repo = NotificationRepository(test_db)
        record = repo.get_by_id(result.notification_id)
        assert record is not None
        assert record.annual_report_id == report.id
        assert record.trigger == NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER

    def test_annual_send_cooldown_blocks_immediate_resend(self, test_db, test_user):
        client = seed_client_identity(
            test_db,
            full_name="Annual Cooldown Client",
            id_number="AIC-002",
            email="annual-cooldown@test.com",
        )
        svc = AnnualReportService(test_db)
        report = svc.create_report(
            client_record_id=client.id,
            tax_year=2024,
            client_type="individual",
            created_by=test_user.id,
            created_by_name=test_user.full_name,
        )
        svc.repo.update(report.id, status=AnnualReportStatus.PENDING_CLIENT)

        r1 = self._send(
            test_db,
            client.id,
            report.id,
            test_user.id,
            idempotency_key="00000000-0000-4000-8000-000000000101",
        )
        assert r1.status in ("sent", "skipped")

        # Ensure first notification is marked SENT so cooldown applies
        if r1.notification_id:
            repo = NotificationRepository(test_db)
            repo.mark_sent(r1.notification_id)
            test_db.commit()

        r2 = self._send(
            test_db,
            client.id,
            report.id,
            test_user.id,
            idempotency_key="00000000-0000-4000-8000-000000000102",
        )
        assert r2.status == "blocked"
        assert r2.notification_id is None
