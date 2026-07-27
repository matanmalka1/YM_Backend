import os
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ["APP_ENV"] = "test"
os.environ.pop("ENV_FILE", None)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5433/binder_crm_test",
)
if len(os.environ.get("JWT_SECRET", "")) < 32:
    os.environ["JWT_SECRET"] = "test-secret-minimum-32-bytes-value"

from sqlalchemy import select

import app.core.background_jobs as background_jobs_module
import app.main as main_module
import app.notes.models.note_entity_note  # noqa: F401
import app.tasks.models.task  # noqa: F401
import app.tax_calendar.models.tax_calendar_deadline_rule  # noqa: F401
import app.tax_calendar.models.tax_calendar_entry  # noqa: F401
from app.clients.models.client_record import ClientRecord  # noqa: F401
from app.database import get_db
from app.legal_entities.models.legal_entity import LegalEntity  # noqa: F401
from app.legal_entities.models.person import Person  # noqa: F401
from app.legal_entities.models.person_legal_entity_link import PersonLegalEntityLink  # noqa: F401
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.services.tax_calendar_bootstrap_service import seed_default_deadline_rules
from app.users.models.user import UserRole
from app.users.services.user_token_service import generate_access_token
from tests.factories import (
    AdvancePaymentFactory,
    AnnualReportFactory,
    AnnualReportModelFactory,
    AuthorityContactFactory,
    BinderFactory,
    BusinessFactory,
    ChargeFactory,
    ClientBusinessFactory,
    ClientFactory,
    NotificationFactory,
    PermanentDocumentFactory,
    SignatureRequestFactory,
    TaskFactory,
    TaxCalendarEntryFactory,
    UserFactory,
    VatWorkItemFactory,
)


@pytest.fixture(scope="function")
def test_db():
    """Run each test in an isolated transaction on the PostgreSQL test database."""
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
        join_transaction_mode="create_savepoint",
    )
    db = TestSessionLocal()
    try:
        connection.execute(text("ALTER SEQUENCE client_office_number_seq RESTART WITH 100001"))
        seed_default_deadline_rules(db)
        for rule in db.scalars(select(DeadlineRule)).all():
            rule.effective_from = date(1900, 1, 1)
        db.flush()
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture(scope="function")
def user_factory(test_db):
    return UserFactory(test_db)


@pytest.fixture
def actor_user(user_factory):
    """Persist a real user for tests that write actor foreign keys."""
    return user_factory(commit=False)


@pytest.fixture(scope="function")
def client_factory(test_db):
    return ClientFactory(test_db)


@pytest.fixture(scope="function")
def business_factory(test_db):
    return BusinessFactory(test_db)


@pytest.fixture(scope="function")
def create_client_with_business(test_db):
    return ClientBusinessFactory(test_db)


@pytest.fixture(scope="function")
def annual_report_factory(test_db, client_factory):
    return AnnualReportFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def annual_report_model_factory(test_db, client_factory, tax_calendar_entry_factory):
    return AnnualReportModelFactory(test_db, client_factory, tax_calendar_entry_factory)


@pytest.fixture(scope="function")
def binder_factory(test_db, client_factory):
    return BinderFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def charge_factory(test_db, client_factory):
    return ChargeFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def task_factory(test_db):
    return TaskFactory(test_db)


@pytest.fixture(scope="function")
def tax_calendar_entry_factory(test_db):
    return TaxCalendarEntryFactory(test_db)


@pytest.fixture(scope="function")
def advance_payment_factory(test_db, client_factory, tax_calendar_entry_factory):
    return AdvancePaymentFactory(test_db, client_factory, tax_calendar_entry_factory)


@pytest.fixture(scope="function")
def permanent_document_factory(test_db, client_factory):
    return PermanentDocumentFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def signature_request_factory(test_db, client_factory):
    return SignatureRequestFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def notification_factory(test_db, client_factory):
    return NotificationFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def vat_work_item_factory(test_db, client_factory, tax_calendar_entry_factory):
    return VatWorkItemFactory(test_db, client_factory, tax_calendar_entry_factory)


@pytest.fixture(scope="function")
def authority_contact_factory(test_db, client_factory):
    return AuthorityContactFactory(test_db, client_factory)


@pytest.fixture(scope="function")
def client(test_db):
    """FastAPI test client with test database."""

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    main_module.app.dependency_overrides[get_db] = override_get_db
    original_expire = background_jobs_module.expire_overdue_requests
    original_signature_service = background_jobs_module.SignatureRequestService
    background_jobs_module.expire_overdue_requests = lambda repo: 0
    background_jobs_module.SignatureRequestService = lambda db: SimpleNamespace(
        reconcile_signed_annual_report_approvals=lambda: SimpleNamespace(
            processed=0,
            submitted=0,
            failed=0,
        )
    )

    with TestClient(main_module.app) as test_client:
        yield test_client

    main_module.app.dependency_overrides.clear()
    background_jobs_module.expire_overdue_requests = original_expire
    background_jobs_module.SignatureRequestService = original_signature_service


@pytest.fixture(scope="function")
def test_user(user_factory):
    """Create test user."""
    return user_factory(
        full_name="Test User",
        email="test@example.com",
        role=UserRole.ADVISOR,
    )


@pytest.fixture(scope="function")
def auth_token(test_user):
    """Generate auth token for test user."""
    return generate_access_token(test_user)


@pytest.fixture(scope="function")
def secretary_user(user_factory):
    """Create secretary user."""
    return user_factory(
        full_name="Test Secretary",
        email="secretary@example.com",
        role=UserRole.SECRETARY,
    )


@pytest.fixture(scope="function")
def secretary_token(secretary_user):
    """Generate auth token for secretary user."""
    return generate_access_token(secretary_user)


@pytest.fixture(scope="function")
def advisor_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="function")
def secretary_headers(secretary_token):
    return {"Authorization": f"Bearer {secretary_token}"}


@pytest.fixture(scope="function")
def vat_client(create_client_with_business):
    """A client fixture for VAT work item tests."""
    client, _ = create_client_with_business(
        full_name="VAT Test Client",
        id_number="123456789",
        opened_at=date.today(),
    )
    return client
