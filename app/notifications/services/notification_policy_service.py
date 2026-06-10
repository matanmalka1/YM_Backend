from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import EntityType
from app.notifications.models.notification import NotificationStatus, NotificationTrigger
from app.notifications.services.constants import (
    ANNUAL_REMINDER_COOLDOWN_DAYS,
    PAYMENT_REMINDER_WARNING_DAYS,
    VAT_REMINDER_WINDOW_DAYS,
)

# Triggers allowed even for FROZEN/CLOSED clients
_FROZEN_CLOSED_ALLOWED = {
    NotificationTrigger.CLIENT_MISSING_INFORMATION,
    NotificationTrigger.CLIENT_DOCUMENTS_REQUEST,
}

from app.annual_reports.models.annual_report_enums import AnnualReportStatus as _ARS

_ANNUAL_REPORT_DOCUMENTS_REQUEST_ALLOWED_STATUSES = frozenset(
    {
        _ARS.NOT_STARTED,
        _ARS.COLLECTING_DOCS,
        _ARS.IN_PREPARATION,
    }
)


@dataclass
class PolicyResult:
    blocked: bool
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


class NotificationPolicyService:
    """
    Business rule gate for sending notifications.

    Contract:
    - blocked=True → caller returns NotificationResult(status=blocked), saves NO record.
    - blocked=False with warnings → caller proceeds, includes warnings in response.
    - Missing Person/email is NOT policy. Handled by contact resolver → produces skipped.
    """

    def can_send(
        self,
        client_record: ClientRecord,
        trigger: NotificationTrigger,
        *,
        db: Session | None = None,
        entity_id: int | None = None,
        annual_report_id: int | None = None,
        confirm_recent_duplicate: bool = False,
    ) -> PolicyResult:
        status = client_record.status

        if status in (ClientStatus.FROZEN, ClientStatus.CLOSED):
            if trigger not in _FROZEN_CLOSED_ALLOWED:
                return PolicyResult(
                    blocked=True,
                    reason="לא ניתן לשלוח הודעות ללקוח שהסטטוס שלו הוא מוקפא או סגור",
                )

        # Binder-specific: validate location_status == READY_FOR_HANDOVER
        if trigger == NotificationTrigger.BINDER_READY_FOR_HANDOVER:
            if db is None or entity_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה קלסר לאימות")
            result = self._check_binder_ready_for_handover(db, entity_id)
            if result is not None:
                return result

        # Annual report triggers
        client_record_id = client_record.id
        if trigger == NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER:
            if db is None or annual_report_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה דוח שנתי לאימות")
            result = self._check_annual_report_client_reminder(
                db, annual_report_id, client_record_id=client_record_id
            )
            if result is not None:
                return result

        if trigger == NotificationTrigger.ANNUAL_REPORT_DOCUMENTS_REQUEST:
            if db is None or annual_report_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה דוח שנתי לאימות")
            result = self._check_annual_report_documents_request(
                db, annual_report_id, client_record_id=client_record_id
            )
            if result is not None:
                return result

        if trigger == NotificationTrigger.VAT_DOCUMENTS_REMINDER:
            if db is None or entity_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה פריט מע״מ לאימות")
            result = self._check_vat_documents_reminder(
                db, entity_id, client_record_id=client_record_id
            )
            if result is not None:
                return result

        if trigger == NotificationTrigger.PAYMENT_REMINDER:
            if db is None or entity_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה חיוב לאימות")
            result = self._check_payment_reminder(
                db,
                entity_id,
                client_record_id=client_record_id,
                confirm_recent_duplicate=confirm_recent_duplicate,
            )
            if result is not None:
                return result

        if trigger == NotificationTrigger.INVOICE_ISSUED:
            if db is None or entity_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה חיוב לאימות")
            result = self._check_invoice_issued(db, entity_id, client_record_id=client_record_id)
            if result is not None:
                return result

        if trigger in (
            NotificationTrigger.SIGNATURE_REQUEST_SENT,
            NotificationTrigger.SIGNATURE_REQUEST_REMINDER,
        ):
            if db is None or entity_id is None:
                return PolicyResult(blocked=True, reason="חסר מזהה בקשת חתימה לאימות")
            result = self._check_signature_request(db, entity_id, client_record_id=client_record_id)
            if result is not None:
                return result

        return PolicyResult(blocked=False)

    def _check_binder_ready_for_handover(self, db: Session, binder_id: int) -> PolicyResult | None:
        from app.binders.models.binder import Binder, BinderLocationStatus

        binder = db.get(Binder, binder_id)
        if binder is None or binder.location_status != BinderLocationStatus.READY_FOR_HANDOVER:
            return PolicyResult(
                blocked=True,
                reason="הקלסר אינו במצב מוכן למסירה",
            )
        return None

    def _check_annual_report_client_reminder(
        self, db: Session, annual_report_id: int, client_record_id: int | None = None
    ) -> PolicyResult | None:
        from app.annual_reports.models.annual_report_enums import AnnualReportStatus
        from app.annual_reports.models.annual_report_model import AnnualReport
        from app.notifications.repositories.notification_repository import NotificationRepository

        report = db.get(AnnualReport, annual_report_id)
        if report is None:
            return PolicyResult(blocked=True, reason="הדוח השנתי לא נמצא")
        if client_record_id is not None and report.client_record_id != client_record_id:
            return PolicyResult(blocked=True, reason="הדוח השנתי לא שייך ללקוח זה")
        if report.status != AnnualReportStatus.PENDING_CLIENT:
            return PolicyResult(
                blocked=True,
                reason="הדוח אינו במצב ממתין לאישור לקוח",
            )

        repo = NotificationRepository(db)
        last = repo.get_last_for_annual_report_trigger(
            annual_report_id, NotificationTrigger.ANNUAL_REPORT_CLIENT_REMINDER
        )
        if last and last.status == NotificationStatus.SENT:
            days_since = (_dt.datetime.now(_dt.UTC) - last.created_at.replace(tzinfo=_dt.UTC)).days
            if days_since < ANNUAL_REMINDER_COOLDOWN_DAYS:
                return PolicyResult(
                    blocked=True,
                    reason=(
                        f"תזכורת נשלחה לפני {days_since} ימים. "
                        f"ניתן לשלוח שוב לאחר {ANNUAL_REMINDER_COOLDOWN_DAYS} ימים."
                    ),
                )
        return None

    def _check_annual_report_documents_request(
        self, db: Session, annual_report_id: int, client_record_id: int | None = None
    ) -> PolicyResult | None:
        from app.annual_reports.models.annual_report_model import AnnualReport

        report = db.get(AnnualReport, annual_report_id)
        if report is None:
            return PolicyResult(blocked=True, reason="הדוח השנתי לא נמצא")
        if client_record_id is not None and report.client_record_id != client_record_id:
            return PolicyResult(blocked=True, reason="הדוח השנתי לא שייך ללקוח זה")
        if report.status not in _ANNUAL_REPORT_DOCUMENTS_REQUEST_ALLOWED_STATUSES:
            return PolicyResult(
                blocked=True,
                reason="הדוח אינו במצב המאפשר שליחת בקשת מסמכים",
            )
        return None

    def _check_vat_documents_reminder(
        self, db: Session, vat_work_item_id: int, client_record_id: int
    ) -> PolicyResult | None:
        from app.legal_entities.models.legal_entity import LegalEntity
        from app.vat.models.vat_enums import VatWorkItemStatus
        from app.vat.models.vat_work_item import VatWorkItem

        item = db.get(VatWorkItem, vat_work_item_id)
        if item is None or item.client_record_id != client_record_id:
            return PolicyResult(blocked=True, reason='פריט מע"מ לא נמצא')

        entity_type = db.scalar(
            select(LegalEntity.entity_type)
            .join(ClientRecord, ClientRecord.legal_entity_id == LegalEntity.id)
            .where(ClientRecord.id == client_record_id)
        )
        if entity_type == EntityType.OSEK_PATUR:
            return PolicyResult(blocked=True, reason='לקוח עוסק פטור אינו חייב בדיווח מע"מ')

        if item.status in (VatWorkItemStatus.FILED, VatWorkItemStatus.CANCELED):
            return PolicyResult(blocked=True, reason='פריט מע"מ כבר הוגש או בוטל')

        if item.due_date_effective is None:
            return PolicyResult(blocked=True, reason='חסר מועד הגשה לפריט מע"מ')

        days_until = (item.due_date_effective - _dt.date.today()).days
        if days_until < 0:
            return PolicyResult(blocked=True, reason='מועד הגשת מע"מ כבר חלף')
        if days_until > VAT_REMINDER_WINDOW_DAYS:
            return PolicyResult(
                blocked=True,
                reason=f'ניתן לשלוח תזכורת מע"מ רק עד {VAT_REMINDER_WINDOW_DAYS} ימים לפני המועד',
            )
        return None

    def _check_payment_reminder(
        self,
        db: Session,
        charge_id: int,
        client_record_id: int,
        confirm_recent_duplicate: bool,
    ) -> PolicyResult | None:
        from app.charges.models.charge import Charge, ChargeStatus
        from app.notifications.repositories.notification_repository import NotificationRepository

        charge = db.get(Charge, charge_id)
        if charge is None or charge.client_record_id != client_record_id:
            return PolicyResult(blocked=True, reason="החיוב לא נמצא")
        if charge.status != ChargeStatus.ISSUED:
            return PolicyResult(blocked=True, reason="ניתן לשלוח תזכורת רק לחיוב שהונפק וטרם שולם")

        if confirm_recent_duplicate:
            return None

        last = NotificationRepository(db).get_last_for_entity_trigger(
            charge_id, NotificationTrigger.PAYMENT_REMINDER
        )
        if last and last.status == NotificationStatus.SENT:
            days_since = (_dt.datetime.now(_dt.UTC) - last.created_at.replace(tzinfo=_dt.UTC)).days
            if days_since < PAYMENT_REMINDER_WARNING_DAYS:
                return PolicyResult(
                    blocked=False,
                    warnings=[
                        (f"תזכורת לתשלום נשלחה לפני {days_since} ימים. ניתן לשלוח שוב לאחר אישור.")
                    ],
                )
        return None

    def _check_invoice_issued(
        self, db: Session, charge_id: int, client_record_id: int
    ) -> PolicyResult | None:
        from app.charges.models.charge import Charge, ChargeStatus

        charge = db.get(Charge, charge_id)
        if charge is None or charge.client_record_id != client_record_id:
            return PolicyResult(blocked=True, reason="החיוב לא נמצא")
        if charge.status not in (ChargeStatus.ISSUED, ChargeStatus.PAID):
            return PolicyResult(blocked=True, reason="ניתן לשלוח הודעת חשבונית רק לחיוב שהונפק")
        return None

    def _check_signature_request(
        self, db: Session, signature_request_id: int, client_record_id: int
    ) -> PolicyResult | None:
        from app.signature_requests.models.signature_request import (
            SignatureRequest,
            SignatureRequestStatus,
        )

        sig = db.get(SignatureRequest, signature_request_id)
        if sig is None or sig.client_record_id != client_record_id:
            return PolicyResult(blocked=True, reason="בקשת החתימה לא נמצאה")
        if sig.status != SignatureRequestStatus.PENDING_SIGNATURE:
            return PolicyResult(blocked=True, reason="בקשת החתימה אינה ממתינה לחתימה")
        if sig.expires_at and _dt.datetime.now(_dt.UTC) > sig.expires_at.replace(tzinfo=_dt.UTC):
            return PolicyResult(blocked=True, reason="בקשת החתימה פגה תוקף")
        if not sig.signing_token:
            return PolicyResult(blocked=True, reason="חסר קישור חתימה פעיל")
        return None
