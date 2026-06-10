# Eagerly import all ORM models so SQLAlchemy can resolve string-based
# relationship() references (e.g. "PermanentDocument", "BinderIntake") before
# configure_mappers() fires. Import order: depended-on models first.
# pylint: disable=unused-import
import app.advance_payments.models.advance_payment  # noqa: F401
import app.annual_reports.models.annual_report_annex_data  # noqa: F401
import app.annual_reports.models.annual_report_credit_point_reason  # noqa: F401
import app.annual_reports.models.annual_report_detail  # noqa: F401
import app.annual_reports.models.annual_report_expense_line  # noqa: F401
import app.annual_reports.models.annual_report_income_line  # noqa: F401
import app.annual_reports.models.annual_report_model  # noqa: F401
import app.annual_reports.models.annual_report_schedule_entry  # noqa: F401
import app.annual_reports.models.annual_report_status_history  # noqa: F401
import app.audit.models.entity_audit_log  # noqa: F401
import app.authority_contacts.models.authority_contact  # noqa: F401
import app.binders.models.binder  # noqa: F401
import app.binders.models.binder_handover  # noqa: F401
import app.binders.models.binder_intake  # noqa: F401
import app.binders.models.binder_intake_edit_log  # noqa: F401
import app.binders.models.binder_intake_material  # noqa: F401
import app.binders.models.binder_lifecycle_log  # noqa: F401
import app.businesses.models.business  # noqa: F401
import app.charges.models.charge  # noqa: F401
import app.clients.models.client_record  # noqa: F401
import app.legal_entities.models.legal_entity  # noqa: F401
import app.legal_entities.models.person  # noqa: F401
import app.legal_entities.models.person_legal_entity_link  # noqa: F401
import app.communications.models.correspondence  # noqa: F401
import app.infrastructure.idempotency.model  # noqa: F401
import app.invoices.models.invoice  # noqa: F401
import app.notes.models.entity_note  # noqa: F401
import app.notifications.models.notification  # noqa: F401
import app.documents.permanent_documents.models.permanent_document  # noqa: F401
import app.reminders.models.reminder  # noqa: F401
import app.signature_requests.models.signature_request  # noqa: F401
import app.tasks.models.task  # noqa: F401
import app.tax_calendar.models.deadline_rule  # noqa: F401
import app.tax_calendar.models.tax_calendar_entry  # noqa: F401
import app.users.models.password_reset_token  # noqa: F401
import app.users.models.user  # noqa: F401
import app.users.models.user_audit_log  # noqa: F401
import app.vat.models.vat_audit_log  # noqa: F401
import app.vat.models.vat_invoice  # noqa: F401
import app.vat.models.vat_work_item  # noqa: F401
