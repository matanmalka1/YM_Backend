import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["APP_ENV"] = "test"
os.environ.pop("ENV_FILE", None)
os.environ.pop("DATABASE_URL", None)
if len(os.environ.get("JWT_SECRET", "")) < 32:
    os.environ["JWT_SECRET"] = "test-secret-minimum-32-bytes-value"

from sqlalchemy import select

import app.core.background_jobs as background_jobs_module
import app.main as main_module
import app.notes.models.entity_note  # noqa: F401
import app.tasks.models.task  # noqa: F401
import app.tax_calendar.models.deadline_rule  # noqa: F401
import app.tax_calendar.models.tax_calendar_entry  # noqa: F401
from app.businesses.models.business import BusinessStatus
from app.clients.enums import ClientStatus
from app.clients.models.client_record import ClientRecord  # noqa: F401
from app.common.enums import IdNumberType
from app.database import Base, get_db
from app.legal_entities.models.legal_entity import LegalEntity  # noqa: F401
from app.legal_entities.models.person import Person  # noqa: F401
from app.legal_entities.models.person_legal_entity_link import PersonLegalEntityLink  # noqa: F401
from app.tax_calendar.models.deadline_rule import DeadlineRule
from app.tax_calendar.services.bootstrap import seed_default_deadline_rules
from app.users.models.user import User, UserRole
from app.users.services.auth_service import AuthService
from app.users.services.token_service import generate_access_token
from tests.helpers.identity import seed_business, seed_client_identity


def _ensure_client_identity_graph(session, client) -> None:
    existing = session.scalars(select(ClientRecord).filter(ClientRecord.id == client.id)).first()
    if existing:
        return
    seeded = seed_client_identity(
        session,
        full_name=client.full_name,
        id_number=client.id_number,
        id_number_type=getattr(client, "id_number_type", IdNumberType.INDIVIDUAL),
        entity_type=getattr(client, "entity_type", None),
        phone=getattr(client, "phone", None),
        email=getattr(client, "email", None),
        address_street=getattr(client, "address_street", None),
        address_building_number=getattr(client, "address_building_number", None),
        address_apartment=getattr(client, "address_apartment", None),
        address_city=getattr(client, "address_city", None),
        address_zip_code=getattr(client, "address_zip_code", None),
        office_client_number=getattr(client, "office_client_number", None),
        notes=getattr(client, "notes", None),
        vat_reporting_frequency=getattr(client, "vat_reporting_frequency", None),
        vat_exempt_ceiling=getattr(client, "vat_exempt_ceiling", None),
        advance_rate=getattr(client, "advance_rate", None),
        advance_rate_updated_at=getattr(client, "advance_rate_updated_at", None),
        accountant_id=getattr(client, "accountant_id", None),
        status=getattr(client, "status", None) or ClientStatus.ACTIVE,
        created_by=getattr(client, "created_by", None),
        deleted_at=getattr(client, "deleted_at", None),
        client_record_id=client.id,
    )
    client.legal_entity_id = seeded.legal_entity_id


@pytest.fixture(scope="function")
def test_db():
    """Create test database with proper SQLite threading config."""
    # Use StaticPool and check_same_thread=False for SQLite in tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestSessionLocal()
    seed_default_deadline_rules(db)
    for rule in db.scalars(select(DeadlineRule)).all():
        rule.effective_from = date(1900, 1, 1)
    db.flush()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def create_client_with_business(test_db):
    """Create a test client with an explicit default business."""

    def _create(
        *,
        full_name: str = "Seeded Test Client",
        id_number: str = "SEEDED-001",
        business_name: str | None = None,
        opened_at: date | None = None,
        **client_fields,
    ):
        client = seed_client_identity(
            full_name=full_name,
            id_number=id_number,
            id_number_type=client_fields.pop("id_number_type", IdNumberType.INDIVIDUAL),
            **client_fields,
            db=test_db,
        )
        business = seed_business(
            test_db,
            legal_entity_id=client.legal_entity_id,
            business_name=business_name or full_name,
            opened_at=opened_at or date.today(),
            status=BusinessStatus.ACTIVE,
        )
        test_db.commit()
        test_db.refresh(business)
        return client, business

    return _create


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
    background_jobs_module.expire_overdue_requests = lambda repo: 0

    with TestClient(main_module.app) as test_client:
        yield test_client

    main_module.app.dependency_overrides.clear()
    background_jobs_module.expire_overdue_requests = original_expire


@pytest.fixture(scope="function")
def test_user(test_db):
    """Create test user."""
    user = User(
        full_name="Test User",
        email="test@example.com",
        password_hash=AuthService.hash_password("password123"),
        role=UserRole.ADVISOR,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_token(test_user):
    """Generate auth token for test user."""
    return generate_access_token(test_user)


@pytest.fixture(scope="function")
def secretary_user(test_db):
    """Create secretary user."""
    user = User(
        full_name="Test Secretary",
        email="secretary@example.com",
        password_hash=AuthService.hash_password("password123"),
        role=UserRole.SECRETARY,
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


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
def vat_client(test_db):
    """A client fixture for VAT work item tests."""
    client = seed_client_identity(
        test_db,
        full_name="VAT Test Client",
        id_number="123456789",
        id_number_type=IdNumberType.INDIVIDUAL,
    )
    seed_business(
        test_db,
        legal_entity_id=client.legal_entity_id,
        business_name=client.full_name,
        status=BusinessStatus.ACTIVE,
        opened_at=date.today(),
    )
    test_db.commit()
    return client
