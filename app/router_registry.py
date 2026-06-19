from fastapi import FastAPI

import app.model_registry  # noqa: F401 — ensures all ORM models are loaded before mappers configure
from app.advance_payments.api.advance_payment_routers import router as advance_payments_router
from app.annual_reports.api.annual_report_routers import router as annual_reports_router
from app.audit.api.audit_routes import router as audit_router
from app.authority_contacts.api.authority_contact_routers import router as authority_contact_router
from app.binders.api.binder_routers import router as binders_router
from app.businesses.api.business_routers import router as businesses_router
from app.charges.api.charge_routers import router as charge_router
from app.clients.api.client_routers import router as clients_router
from app.communications.api.correspondence_routers import router as correspondence_router
from app.dashboard.api.dashboard_routers import router as dashboard_router
from app.documents.permanent_documents.api.permanent_document_routers import (
    router as permanent_documents_router,
)
from app.health.api.health_routers import router as health_router
from app.invoices.api.invoice_routers import router as invoice_router
from app.notes.api.note_routers import router as notes_router
from app.notifications.api.notification_routers import router as notification_router
from app.reminders.api import reminder_routers as reminders
from app.reports.api.report_routers import router as reports_router
from app.search.api.search_routers import router as search_router
from app.signature_requests.api import signature_request_routers as signature_requests_routers
from app.tasks.api.task_routes import router as tasks_router
from app.tax_calendar.api.tax_calendar_routers import router as tax_calendar_router
from app.timeline.api.timeline_routers import router as timeline_router
from app.users.api.user_routers import router as users_router
from app.vat.api.vat_routers import router as vat_reports_router
from app.work_queue.api.work_queue_routes import router as work_queue_router


def register_routers(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(annual_reports_router, prefix="/api/v1")
    app.include_router(tax_calendar_router, prefix="/api/v1")
    app.include_router(authority_contact_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(clients_router, prefix="/api/v1")
    app.include_router(businesses_router, prefix="/api/v1")
    app.include_router(binders_router, prefix="/api/v1")
    app.include_router(charge_router, prefix="/api/v1")
    app.include_router(invoice_router, prefix="/api/v1")
    app.include_router(permanent_documents_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(reminders.router, prefix="/api/v1")
    app.include_router(notification_router, prefix="/api/v1")
    app.include_router(correspondence_router, prefix="/api/v1")
    app.include_router(advance_payments_router, prefix="/api/v1")
    app.include_router(signature_requests_routers.router, prefix="/api/v1")
    app.include_router(signature_requests_routers.signer_router)
    app.include_router(vat_reports_router, prefix="/api/v1")
    app.include_router(notes_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(work_queue_router, prefix="/api/v1")
