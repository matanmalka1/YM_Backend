"""
Resolves template context variables from DB entities given a trigger + entity_id.

Resolves binder, annual report, charge, VAT, signature, and client-level
template context.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.annual_reports.repositories.annual_report_report_repository import (
    AnnualReportRootRepository,
)
from app.binders.repositories.binder_repository import BinderRepository
from app.charges.repositories.charge_repository import ChargeRepository
from app.clients.repositories.client_identity_repository import ClientIdentityRepository
from app.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.logging_config import get_logger
from app.legal_entities.models.person import Person
from app.notifications.models.notification import NotificationTrigger
from app.signature_requests.repositories.signature_request_repository import (
    SignatureRequestRepository,
)
from app.users.repositories.user_repository import UserRepository
from app.vat.repositories.vat_work_item_query_repository import VatWorkItemQueryRepository

logger = get_logger(__name__)

_BINDER_TRIGGERS = {
    NotificationTrigger.BINDER_READY_FOR_HANDOVER,
    NotificationTrigger.BINDER_MISSING_DOCUMENTS,
    NotificationTrigger.BINDER_GENERAL_REMINDER,
}

_ANNUAL_REPORT_TRIGGERS = {
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


class NotificationContextResolver:
    def __init__(self, db: Session):
        self.db = db
        self.client_identity_repo = ClientIdentityRepository(db)
        self.user_repo = UserRepository(db)
        self.binder_repo = BinderRepository(db)
        self.annual_report_repo = AnnualReportRootRepository(db)
        self.charge_repo = ChargeRepository(db)
        self.vat_repo = VatWorkItemQueryRepository(db)
        self.signature_repo = SignatureRequestRepository(db)

    def resolve(
        self,
        trigger: NotificationTrigger,
        client_record_id: int,
        entity_id: int | None,
        business_id: int | None,  # noqa: ARG002 — reserved for Phase 2+ domain resolvers
        triggered_by_user_id: int | None,
        extra: dict | None = None,
    ) -> dict:
        """
        Build template context dict for the given trigger.
        Raises NotFoundError if a required entity is not found.
        extra: caller-supplied values (e.g. message for client_general_message).
        """
        ctx: dict = {}

        # Base: office_name, sender_name
        ctx["office_name"] = settings.EMAIL_FROM_NAME or "המשרד"
        ctx["sender_name"] = self._resolve_sender_name(triggered_by_user_id)

        # Binder triggers require binder_number
        if trigger in _BINDER_TRIGGERS:
            if entity_id is not None:
                binder_number = self._resolve_binder_number(entity_id, client_record_id)
                ctx["binder_number"] = binder_number

        # Annual report triggers require tax_year; ownership validated against client_record_id
        if trigger in _ANNUAL_REPORT_TRIGGERS:
            if entity_id is not None:
                ctx["tax_year"] = self._resolve_annual_report_tax_year(entity_id, client_record_id)

        if trigger in _CHARGE_TRIGGERS:
            if entity_id is not None:
                ctx.update(self._resolve_charge_context(entity_id, client_record_id))

        if trigger == NotificationTrigger.VAT_DOCUMENTS_REMINDER:
            if entity_id is not None:
                ctx.update(self._resolve_vat_context(entity_id, client_record_id))

        if trigger in _SIGNATURE_TRIGGERS:
            if entity_id is not None:
                ctx.update(self._resolve_signature_context(entity_id, client_record_id))

        # Client-level triggers that take a free-text message.
        # Default empty string so preview renders without blocking on missing var.
        # The actual message is provided by the user after editing subject/body.
        if trigger in (
            NotificationTrigger.BINDER_GENERAL_REMINDER,
            NotificationTrigger.BINDER_MISSING_DOCUMENTS,
            NotificationTrigger.CLIENT_MISSING_INFORMATION,
            NotificationTrigger.CLIENT_DOCUMENTS_REQUEST,
            NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        ):
            ctx["message"] = extra.get("message", "") if extra else ""

        return ctx

    def resolve_person(self, client_record_id: int) -> Person | None:
        """Return the OWNER Person for the client record, or None."""
        return self.client_identity_repo.get_owner_person(client_record_id)

    def resolve_client_name(self, client_record_id: int) -> str:
        """Return display name: Person.full_name → LegalEntity.official_name → fallback."""
        from app.notifications.notification_messages import FALLBACK_CLIENT_NAME

        person = self.resolve_person(client_record_id)
        if person and person.full_name:
            return person.full_name

        return self.client_identity_repo.get_official_name(client_record_id) or FALLBACK_CLIENT_NAME

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_sender_name(self, user_id: int | None) -> str:
        if user_id is None:
            return "צוות המשרד"
        user = self.user_repo.get(user_id, include_deleted=True)
        if user and user.full_name:
            return user.full_name
        return "צוות המשרד"

    def _resolve_binder_number(self, binder_id: int, client_record_id: int) -> str:
        binder = self.binder_repo.get(binder_id, include_deleted=True)
        if binder is None or binder.client_record_id != client_record_id:
            raise NotFoundError("הקלסר לא נמצא", ErrorCode.BINDER_NOT_FOUND)
        return binder.binder_number

    def _resolve_annual_report_tax_year(self, annual_report_id: int, client_record_id: int) -> int:
        report = self.annual_report_repo.get(annual_report_id, include_deleted=True)
        if report is None or report.client_record_id != client_record_id:
            raise NotFoundError("הדוח השנתי לא נמצא", ErrorCode.ANNUAL_REPORT_NOT_FOUND)
        return report.tax_year

    def _resolve_charge_context(self, charge_id: int, client_record_id: int) -> dict:
        charge = self.charge_repo.get(charge_id, include_deleted=True)
        if charge is None or charge.client_record_id != client_record_id:
            raise NotFoundError("החיוב לא נמצא", ErrorCode.CHARGE_NOT_FOUND)
        amount = int(charge.amount) if charge.amount == int(charge.amount) else float(charge.amount)
        return {
            "charge_amount": str(amount),
            "charge_description": charge.description or "",
            "issued_at": charge.issued_at.strftime("%d/%m/%Y") if charge.issued_at else "",
        }

    def _resolve_vat_context(self, vat_work_item_id: int, client_record_id: int) -> dict:
        from app.utils.time_utils import israel_today

        item = self.vat_repo.get(vat_work_item_id, include_deleted=True)
        if item is None or item.client_record_id != client_record_id:
            raise NotFoundError('פריט מע"מ לא נמצא', ErrorCode.VAT_NOT_FOUND)
        deadline = item.due_date_effective
        today = israel_today()
        days_until = (deadline - today).days if deadline else None
        deadline_note = " — היום הוא המועד האחרון!" if days_until == 0 else ""
        return {
            "period": item.period,
            "deadline": deadline.strftime("%d/%m/%Y") if deadline else "",
            "days_until_deadline": str(days_until) if days_until is not None else "",
            "deadline_note": deadline_note,
        }

    def _resolve_signature_context(self, signature_request_id: int, client_record_id: int) -> dict:
        sig = self.signature_repo.get_by_id(signature_request_id, include_deleted=True)
        if sig is None or sig.client_record_id != client_record_id:
            raise NotFoundError("בקשת חתימה לא נמצאה", ErrorCode.SIGNATURE_REQUEST_NOT_FOUND)
        signature_link = (
            f"{settings.FRONTEND_BASE_URL}/sign/{sig.signing_token}" if sig.signing_token else ""
        )
        return {
            "document_title": sig.title,
            "signature_link": signature_link,
            "expires_at": sig.expires_at.strftime("%d/%m/%Y") if sig.expires_at else "",
        }
