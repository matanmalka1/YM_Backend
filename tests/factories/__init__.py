"""Public assembly surface for domain-owned test factories."""

from tests.factories.advance_payments import AdvancePaymentFactory
from tests.factories.annual_reports import (
    AnnualReportRowFactory,
    AnnualReportServiceFactory,
)
from tests.factories.billing import ChargeFactory, InvoiceFactory
from tests.factories.binders import (
    BinderFactory,
    BinderIntakeFactory,
    BinderIntakeMaterialFactory,
)
from tests.factories.clients import BusinessFactory, ClientBusinessFactory, ClientFactory
from tests.factories.communications import AuthorityContactFactory
from tests.factories.documents import PermanentDocumentFactory
from tests.factories.notifications import NotificationFactory
from tests.factories.signature_requests import SignatureRequestFactory
from tests.factories.tasks import ReminderFactory, TaskFactory
from tests.factories.tax_calendar import TaxCalendarEntryFactory
from tests.factories.users import UserFactory
from tests.factories.vat import VatWorkItemFactory

__all__ = [
    "AdvancePaymentFactory",
    "AnnualReportServiceFactory",
    "AnnualReportRowFactory",
    "AuthorityContactFactory",
    "BinderFactory",
    "BinderIntakeFactory",
    "BinderIntakeMaterialFactory",
    "BusinessFactory",
    "ChargeFactory",
    "ClientBusinessFactory",
    "ClientFactory",
    "InvoiceFactory",
    "NotificationFactory",
    "PermanentDocumentFactory",
    "ReminderFactory",
    "SignatureRequestFactory",
    "TaskFactory",
    "TaxCalendarEntryFactory",
    "UserFactory",
    "VatWorkItemFactory",
]
