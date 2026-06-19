"""
Resolves template context variables from DB entities given a trigger + entity_id.

Resolves binder, annual report, charge, VAT, signature, and client-level
template context.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.models.client_record import ClientRecord
from app.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.core.logging_config import get_logger
from app.legal_entities.models.legal_entity import LegalEntity
from app.legal_entities.models.person import Person
from app.legal_entities.models.person_legal_entity_link import (
    PersonLegalEntityLink,
    PersonLegalEntityRole,
)
from app.notifications.models.notification import NotificationTrigger
from app.users.models.user import User

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
        return self.db.execute(
            select(Person)
            .select_from(ClientRecord)
            .join(LegalEntity, LegalEntity.id == ClientRecord.legal_entity_id)
            .outerjoin(
                PersonLegalEntityLink,
                (PersonLegalEntityLink.legal_entity_id == LegalEntity.id)
                & (PersonLegalEntityLink.role == PersonLegalEntityRole.OWNER),
            )
            .outerjoin(Person, Person.id == PersonLegalEntityLink.person_id)
            .where(ClientRecord.id == client_record_id)
        ).scalar()

    def resolve_client_name(self, client_record_id: int) -> str:
        """Return display name: Person.full_name → LegalEntity.official_name → fallback."""
        from app.notifications.notification_messages import FALLBACK_CLIENT_NAME

        person = self.resolve_person(client_record_id)
        if person and person.full_name:
            return person.full_name

        row = self.db.execute(
            select(LegalEntity.official_name)
            .join(ClientRecord, ClientRecord.legal_entity_id == LegalEntity.id)
            .where(ClientRecord.id == client_record_id)
        ).scalar()
        return row or FALLBACK_CLIENT_NAME

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_sender_name(self, user_id: int | None) -> str:
        if user_id is None:
            return "צוות המשרד"
        user = self.db.get(User, user_id)
        if user and user.full_name:
            return user.full_name
        return "צוות המשרד"

    def _resolve_binder_number(self, binder_id: int, client_record_id: int) -> str:
        from app.binders.models.binder import Binder

        binder = self.db.get(Binder, binder_id)
        if binder is None or binder.client_record_id != client_record_id:
            raise NotFoundError("הקלסר לא נמצא", ErrorCode.BINDER_NOT_FOUND)
        return binder.binder_number

    def _resolve_annual_report_tax_year(self, annual_report_id: int, client_record_id: int) -> int:
        from app.annual_reports.models.annual_report_model import AnnualReport

        report = self.db.get(AnnualReport, annual_report_id)
        if report is None or report.client_record_id != client_record_id:
            raise NotFoundError("הדוח השנתי לא נמצא", ErrorCode.ANNUAL_REPORT_NOT_FOUND)
        return report.tax_year

    def _resolve_charge_context(self, charge_id: int, client_record_id: int) -> dict:
        from app.charges.models.charge import Charge

        charge = self.db.get(Charge, charge_id)
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
        from app.vat.models.vat_work_item import VatWorkItem

        item = self.db.get(VatWorkItem, vat_work_item_id)
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
        from app.signature_requests.models.signature_request import SignatureRequest

        sig = self.db.get(SignatureRequest, signature_request_id)
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
