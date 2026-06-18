from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, NotFoundError
from app.core.logging_config import get_logger
from app.infrastructure.notifications import EmailChannel
from app.notifications.models.notification import (
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.notifications.repositories.notification_repository import NotificationRepository
from app.notifications.schemas.notification_schemas import (
    NotificationPreviewRequest,
    NotificationPreviewResponse,
    NotificationResult,
    NotificationSendRequest,
)
from app.notifications.services.constants import (
    BODY_MAX_LENGTH,
    NOTIFICATION_IDEMPOTENCY_TTL_HOURS,
    SUBJECT_MAX_LENGTH,
)
from app.notifications.services.notification_context_resolver import (
    NotificationContextResolver,
)
from app.notifications.services.notification_delivery_service import (
    NotificationDeliveryService,
)
from app.notifications.services.notification_policy_service import (
    NotificationPolicyService,
)
from app.notifications.services.notification_template_renderer import (
    NotificationTemplateRenderer,
)

# Triggers that are auto-only and must never reach the manual send path.
_AUTO_ONLY_TRIGGERS = {NotificationTrigger.BINDER_READY_FOR_HANDOVER}

# Manual triggers that require entity_id (annual_report.id).
_ANNUAL_TRIGGERS = {
    NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
    NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
}

_CHARGE_TRIGGERS = {
    NotificationTrigger.INVOICE_ISSUED,
    NotificationTrigger.PAYMENT_REMINDER,
}

_SIGNATURE_TRIGGERS = {
    NotificationTrigger.SIGNATURE_REQUEST_SENT,
    NotificationTrigger.SIGNATURE_REQUEST_REMINDER,
}

_GENERIC_ENTITY_TRIGGERS = (
    _CHARGE_TRIGGERS | {NotificationTrigger.VAT_DOCUMENTS_REMINDER} | _SIGNATURE_TRIGGERS
)
logger = get_logger(__name__)


def _hash_request(
    trigger: str,
    channel: str,
    subject: str,
    body: str,
    client_record_id: int,
    entity_id: int | None,
    business_id: int | None,
) -> str:
    payload = json.dumps(
        {
            "trigger": trigger,
            "channel": channel,
            "subject": subject,
            "body": body,
            "cr": client_record_id,
            "entity_id": entity_id,
            "business_id": business_id,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class NotificationSendService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = NotificationRepository(db)
        self.policy = NotificationPolicyService()
        self.renderer = NotificationTemplateRenderer()
        self.resolver = NotificationContextResolver(db)
        live = settings.APP_ENV in ("staging", "production")
        self._email = EmailChannel(
            enabled=settings.NOTIFICATIONS_ENABLED and live,
            api_key=settings.BREVO_API_KEY,
            api_url=settings.BREVO_API_URL,
            from_address=settings.EMAIL_FROM_ADDRESS,
            from_name=settings.EMAIL_FROM_NAME,
        )
        self._delivery = NotificationDeliveryService()

    # ── Preview ───────────────────────────────────────────────────────────────

    def preview(
        self,
        request: NotificationPreviewRequest,
        triggered_by: int,
    ) -> NotificationPreviewResponse:
        if request.trigger in _AUTO_ONLY_TRIGGERS:
            raise AppError(
                "הודעה זו נשלחת אוטומטית ואינה זמינה לשליחה ידנית",
                ErrorCode.NOTIFICATION_AUTO_ONLY_TRIGGER,
            )
        if request.trigger in _ANNUAL_TRIGGERS and not request.entity_id:
            raise AppError(
                "חובה לספק מזהה דוח שנתי לסוג הודעה זה", ErrorCode.NOTIFICATION_MISSING_ENTITY_ID
            )
        if request.trigger in _GENERIC_ENTITY_TRIGGERS and not request.entity_id:
            raise AppError(
                "חובה לספק מזהה ישות לסוג הודעה זה", ErrorCode.NOTIFICATION_MISSING_ENTITY_ID
            )

        client_record = self.db.get(ClientRecord, request.client_record_id)
        if client_record is None:
            raise NotFoundError("הלקוח לא נמצא", ErrorCode.CLIENT_RECORD_NOT_FOUND)

        annual_report_id = (
            request.entity_id
            if request.trigger
            in (
                NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
                NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
            )
            else None
        )
        policy = self.policy.can_send(
            client_record,
            request.trigger,
            db=self.db,
            entity_id=request.entity_id,
            annual_report_id=annual_report_id,
            confirm_recent_duplicate=request.confirm_recent_duplicate,
        )
        if policy.blocked:
            return NotificationPreviewResponse(
                can_send=False,
                status="blocked",
                reason=policy.reason,
                warnings=policy.warnings,
            )

        if request.trigger in _SIGNATURE_TRIGGERS:
            recipient = self._resolve_signer_email(request.entity_id)
        else:
            person = self.resolver.resolve_person(request.client_record_id)
            recipient = person.email if person else None
        person_name = self.resolver.resolve_client_name(request.client_record_id)

        ctx = self.resolver.resolve(
            trigger=request.trigger,
            client_record_id=request.client_record_id,
            entity_id=request.entity_id,
            business_id=request.business_id,
            triggered_by_user_id=triggered_by,
        )

        body, subject, error_reason = self.renderer.build_preview(request.trigger, ctx, person_name)
        if error_reason:
            return NotificationPreviewResponse(
                can_send=False,
                status="blocked",
                reason=error_reason,
                warnings=policy.warnings,
            )

        return NotificationPreviewResponse(
            can_send=True,
            status="ready",
            warnings=policy.warnings,
            recipient=recipient,
            subject=subject,
            body=body,
        )

    # ── Send ──────────────────────────────────────────────────────────────────

    def send(
        self,
        request: NotificationSendRequest,
        triggered_by: int,
        idempotency_key: str,
    ) -> NotificationResult:
        if request.trigger in _AUTO_ONLY_TRIGGERS:
            raise AppError(
                "הודעה זו נשלחת אוטומטית ואינה זמינה לשליחה ידנית",
                ErrorCode.NOTIFICATION_AUTO_ONLY_TRIGGER,
            )
        if request.trigger in _ANNUAL_TRIGGERS and not request.entity_id:
            raise AppError(
                "חובה לספק מזהה דוח שנתי לסוג הודעה זה", ErrorCode.NOTIFICATION_MISSING_ENTITY_ID
            )
        if request.trigger in _GENERIC_ENTITY_TRIGGERS and not request.entity_id:
            raise AppError(
                "חובה לספק מזהה ישות לסוג הודעה זה", ErrorCode.NOTIFICATION_MISSING_ENTITY_ID
            )

        client_record = self.db.get(ClientRecord, request.client_record_id)
        if client_record is None:
            raise NotFoundError("הלקוח לא נמצא", ErrorCode.CLIENT_RECORD_NOT_FOUND)

        # Policy check — blocked = no record created
        annual_report_id_for_policy = (
            request.entity_id
            if request.trigger
            in (
                NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER,
                NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST,
            )
            else None
        )
        policy = self.policy.can_send(
            client_record,
            request.trigger,
            db=self.db,
            entity_id=request.entity_id,
            annual_report_id=annual_report_id_for_policy,
            confirm_recent_duplicate=request.confirm_recent_duplicate,
        )
        if policy.blocked:
            return NotificationResult(
                status="blocked",
                reason=policy.reason,
                warnings=policy.warnings,
            )

        overrides = request.overrides
        needs_default_subject = overrides is None or overrides.subject is None
        needs_default_body = overrides is None or overrides.body is None
        default_subject = ""
        default_body = ""
        if needs_default_subject or needs_default_body:
            person_name = self.resolver.resolve_client_name(request.client_record_id)
            ctx = self.resolver.resolve(
                trigger=request.trigger,
                client_record_id=request.client_record_id,
                entity_id=request.entity_id,
                business_id=request.business_id,
                triggered_by_user_id=triggered_by,
            )
            default_body, default_subject, error_reason = self.renderer.build_preview(
                request.trigger, ctx, person_name
            )
            if error_reason:
                return NotificationResult(
                    status="blocked",
                    reason=error_reason,
                    warnings=policy.warnings,
                )

        subject_value = (
            overrides.subject
            if overrides is not None and overrides.subject is not None
            else default_subject
        )
        body_value = (
            overrides.body if overrides is not None and overrides.body is not None else default_body
        )

        # Validate subject/body after policy — blocked clients don't raise validation errors
        subject = subject_value.strip()
        body = body_value.strip()
        _placeholder_re = re.compile(r"\{[a-z_]+\}")
        if not subject:
            raise AppError("נושא ההודעה לא יכול להיות ריק", ErrorCode.NOTIFICATION_EMPTY_SUBJECT)
        if not body:
            raise AppError("גוף ההודעה לא יכול להיות ריק", ErrorCode.NOTIFICATION_EMPTY_BODY)
        if len(subject) > SUBJECT_MAX_LENGTH:
            raise AppError(
                f"הנושא ארוך מדי (מקסימום {SUBJECT_MAX_LENGTH} תווים)",
                ErrorCode.NOTIFICATION_SUBJECT_TOO_LONG,
            )
        if len(body) > BODY_MAX_LENGTH:
            raise AppError(
                f"גוף ההודעה ארוך מדי (מקסימום {BODY_MAX_LENGTH} תווים)",
                ErrorCode.NOTIFICATION_BODY_TOO_LONG,
            )
        if _placeholder_re.search(subject) or _placeholder_re.search(body):
            raise AppError(
                "ההודעה מכילה שדות שלא מולאו", ErrorCode.NOTIFICATION_VISIBLE_PLACEHOLDER
            )

        channel = NotificationChannel(request.channel or NotificationChannel.EMAIL.value)
        req_hash = _hash_request(
            request.trigger.value,
            channel.value,
            subject,
            body,
            request.client_record_id,
            request.entity_id,
            request.business_id,
        )

        existing = self.repo.find_by_idempotency_key(
            idempotency_key,
            ttl_hours=NOTIFICATION_IDEMPOTENCY_TTL_HOURS,
        )
        if existing is not None:
            if existing.request_hash != req_hash:
                logger.warning(
                    "idempotency key reused with different payload key=%s",
                    idempotency_key,
                )
            # A PENDING row means a prior attempt crashed mid-flight.
            # Fall through and let this request proceed normally.
            if existing.status != NotificationStatus.PENDING:
                return NotificationResult(
                    status=existing.status.value,  # type: ignore[arg-type]
                    notification_id=existing.id,
                    reason="כבר נשלח (idempotency)",
                )

        # Contact resolution — skipped = record saved with recipient=null
        if request.trigger in _SIGNATURE_TRIGGERS:
            recipient = self._resolve_signer_email(request.entity_id)
        else:
            person = self.resolver.resolve_person(request.client_record_id)
            recipient = person.email if person else None

        # Derive entity anchors from trigger so domain-level fields (e.g. annual_report_id)
        # are populated and cooldown / history queries work correctly.
        annual_report_id = request.entity_id if request.trigger in _ANNUAL_TRIGGERS else None
        entity_type_for_annual = "annual_report" if request.trigger in _ANNUAL_TRIGGERS else None
        signature_request_id = request.entity_id if request.trigger in _SIGNATURE_TRIGGERS else None
        entity_type = (
            entity_type_for_annual
            or ("signature_request" if request.trigger in _SIGNATURE_TRIGGERS else None)
            or ("charge" if request.trigger in _CHARGE_TRIGGERS else None)
            or (
                "vat_work_item"
                if request.trigger == NotificationTrigger.VAT_DOCUMENTS_REMINDER
                else None
            )
        )

        if not recipient:
            n = self.repo.create(
                client_record_id=request.client_record_id,
                trigger=request.trigger,
                channel=channel,
                recipient=None,
                content_snapshot=body,
                subject_snapshot=subject,
                business_id=request.business_id,
                annual_report_id=annual_report_id,
                signature_request_id=signature_request_id,
                entity_type=entity_type,
                entity_id=request.entity_id,
                triggered_by=triggered_by,
                idempotency_key=idempotency_key,
                request_hash=req_hash,
                status=NotificationStatus.SKIPPED,
            )
            logger.info(
                "notification skipped: no email | client=%s trigger=%s id=%s",
                request.client_record_id,
                request.trigger.value,
                n.id,
            )
            return NotificationResult(
                status="skipped",
                notification_id=n.id,
                reason="לא נמצאה כתובת אימייל עבור הלקוח",
                warnings=policy.warnings,
            )

        delivery_recipient = recipient

        n = self.repo.create(
            client_record_id=request.client_record_id,
            trigger=request.trigger,
            channel=channel,
            recipient=delivery_recipient,
            content_snapshot=body,
            subject_snapshot=subject,
            business_id=request.business_id,
            annual_report_id=annual_report_id,
            signature_request_id=signature_request_id,
            entity_type=entity_type,
            entity_id=request.entity_id,
            triggered_by=triggered_by,
            idempotency_key=idempotency_key,
            request_hash=req_hash,
            status=NotificationStatus.PENDING,
        )

        ok, err = self._delivery.send(
            recipient=delivery_recipient,
            subject=subject,
            body=body,
            email_channel=self._email,
        )

        if ok:
            self.repo.mark_sent(n.id)
            return NotificationResult(
                status="sent",
                notification_id=n.id,
                warnings=policy.warnings,
            )

        self.repo.mark_failed(n.id, err or "delivery failed")
        return NotificationResult(
            status="failed",
            notification_id=n.id,
            reason=err,
            warnings=policy.warnings,
        )

    def _resolve_signer_email(self, signature_request_id: int | None) -> str | None:
        if signature_request_id is None:
            return None
        from app.signature_requests.models.signature_request import SignatureRequest

        sig = self.db.get(SignatureRequest, signature_request_id)
        return sig.signer_email if sig else None
