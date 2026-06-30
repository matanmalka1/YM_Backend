from __future__ import annotations

from datetime import date
from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.annual_reports.services.annual_report_service import AnnualReportService
from app.businesses.models.business import Business, BusinessStatus
from app.common.enums import IdNumberType
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from tests.helpers.identity import (
    SeededClient,
    seed_business,
    seed_client_identity,
    seed_client_with_business,
)


def create_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str = "password123",
    role: UserRole = UserRole.ADVISOR,
    is_active: bool = True,
    commit: bool = False,
) -> User:
    user = User(
        full_name=full_name,
        email=email,
        password_hash=AuthService.hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    if commit:
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    return user


class UserFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        full_name: str = "Test User",
        email: str | None = None,
        password: str = "password123",
        role: UserRole = UserRole.ADVISOR,
        is_active: bool = True,
        commit: bool = True,
    ) -> User:
        sequence = next(self._sequence)
        return create_user(
            self.db,
            full_name=full_name,
            email=email or f"test-user-{sequence}@example.com",
            password=password,
            role=role,
            is_active=is_active,
            commit=commit,
        )


class ClientFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        full_name: str | None = None,
        id_number: str | None = None,
        commit: bool = False,
        **client_fields: Any,
    ) -> SeededClient:
        sequence = next(self._sequence)
        client = seed_client_identity(
            self.db,
            full_name=full_name or f"Test Client {sequence}",
            id_number=id_number or f"TEST-CLIENT-{sequence:06d}",
            **client_fields,
        )
        if commit:
            self.db.commit()
        return client


class BusinessFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        legal_entity_id: int,
        business_name: str | None = None,
        opened_at: date | None = None,
        status: BusinessStatus = BusinessStatus.ACTIVE,
        created_by: int | None = None,
        notes: str | None = None,
        commit: bool = False,
    ) -> Business:
        sequence = next(self._sequence)
        business = seed_business(
            self.db,
            legal_entity_id=legal_entity_id,
            business_name=business_name or f"Test Business {sequence}",
            opened_at=opened_at,
            status=status,
            created_by=created_by,
            notes=notes,
        )
        if commit:
            self.db.commit()
            self.db.refresh(business)
        return business


class ClientBusinessFactory:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        full_name: str | None = None,
        id_number: str | None = None,
        business_name: str | None = None,
        id_number_type: IdNumberType = IdNumberType.INDIVIDUAL,
        opened_at: date | None = None,
        business_status: BusinessStatus = BusinessStatus.ACTIVE,
        business_created_by: int | None = None,
        business_notes: str | None = None,
        commit: bool = True,
        **client_fields: Any,
    ) -> tuple[SeededClient, Business]:
        sequence = next(self._sequence)
        resolved_name = full_name or f"Test Client {sequence}"
        client, business = seed_client_with_business(
            self.db,
            full_name=resolved_name,
            id_number=id_number or f"TEST-BUSINESS-CLIENT-{sequence:06d}",
            business_name=business_name,
            id_number_type=id_number_type,
            opened_at=opened_at,
            business_status=business_status,
            business_created_by=business_created_by,
            business_notes=business_notes,
            **client_fields,
        )
        if commit:
            self.db.commit()
            self.db.refresh(business)
        return client, business


class AnnualReportFactory:
    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory

    def __call__(
        self,
        *,
        client: SeededClient | None = None,
        client_record_id: int | None = None,
        client_full_name: str | None = None,
        client_id_number: str | None = None,
        actor: User | None = None,
        created_by: int | None = None,
        created_by_name: str | None = None,
        tax_year: int = 2026,
        client_type: str = "corporation",
        deadline_type: str = "standard",
        **report_fields: Any,
    ):
        if client is not None and client_record_id is not None:
            raise ValueError("Pass either client or client_record_id, not both")
        if client is None and client_record_id is None:
            client = self.client_factory(
                full_name=client_full_name,
                id_number=client_id_number,
            )
        assert client_record_id is not None or client is not None
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        resolved_actor_id = created_by if created_by is not None else actor.id if actor else 1
        resolved_actor_name = created_by_name or (actor.full_name if actor else "Test User")
        return AnnualReportService(self.db).create_report(
            client_record_id=resolved_client_id,
            tax_year=tax_year,
            client_type=client_type,
            created_by=resolved_actor_id,
            created_by_name=resolved_actor_name,
            deadline_type=deadline_type,
            **report_fields,
        )
