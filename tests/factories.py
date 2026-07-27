from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from itertools import count
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advance_payments.models.advance_payment import (
    AdvancePayment,
    AdvancePaymentStatus,
    PaymentMethod,
    TurnoverSource,
)
from app.annual_reports.services.annual_report_service import AnnualReportService
from app.authority_contacts.models.authority_contact import AuthorityContact, ContactType
from app.binders.models.binder import Binder, BinderCapacityStatus, BinderLocationStatus
from app.businesses.models.business import Business, BusinessStatus
from app.charges.models.charge import Charge, ChargeStatus, ChargeType
from app.clients.client_enums import ClientStatus
from app.clients.models.client_record import ClientRecord
from app.common.enums import (
    DeadlineRuleType,
    IdNumberType,
    ObligationType,
    SubmissionMethod,
    VatType,
)
from app.documents.permanent_documents.models.permanent_document import (
    DocumentScope,
    DocumentStatus,
    PermanentDocument,
    PermanentDocumentType,
)
from app.legal_entities.models.legal_entity import LegalEntity
from app.notifications.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTrigger,
)
from app.signature_requests.models.signature_request import (
    SignatureRequest,
    SignatureRequestStatus,
    SignatureRequestType,
)
from app.tasks.models.task import Task, TaskPriority, TaskStatus
from app.tax_calendar.models.tax_calendar_deadline_rule import DeadlineRule
from app.tax_calendar.models.tax_calendar_entry import TaxCalendarEntry
from app.users.models.user import User, UserRole
from app.users.services.user_auth_service import AuthService
from app.vat.models.vat_enums import VatWorkItemStatus
from app.vat.models.vat_work_item import VatWorkItem
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


# ClientRecord-level fields ClientFactory can still honour when it reuses an existing
# LegalEntity. Anything else in **client_fields targets LegalEntity/Person, which are not
# rewritten in that branch.
_EXISTING_ENTITY_CLIENT_FIELDS = frozenset(
    {
        "client_record_id",
        "office_client_number",
        "accountant_id",
        "status",
        "notes",
        "created_by",
        "deleted_at",
    }
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
        legal_entity_id: int | None = None,
        commit: bool = False,
        **client_fields: Any,
    ) -> SeededClient:
        sequence = next(self._sequence)
        if legal_entity_id is None:
            client = seed_client_identity(
                self.db,
                full_name=full_name or f"Test Client {sequence}",
                id_number=id_number or f"TEST-CLIENT-{sequence:06d}",
                **client_fields,
            )
        else:
            unsupported = set(client_fields) - _EXISTING_ENTITY_CLIENT_FIELDS
            if unsupported:
                raise ValueError(
                    "These fields belong to LegalEntity/Person and are ignored when "
                    f"legal_entity_id is passed: {sorted(unsupported)}"
                )
            legal_entity = self.db.get(LegalEntity, legal_entity_id)
            if legal_entity is None:
                raise ValueError(f"LegalEntity id={legal_entity_id} does not exist")
            person = legal_entity.person_links[0].person if legal_entity.person_links else None
            record = ClientRecord(
                id=client_fields.get("client_record_id"),
                legal_entity_id=legal_entity.id,
                office_client_number=client_fields.get("office_client_number"),
                accountant_id=client_fields.get("accountant_id"),
                status=client_fields.get("status", ClientStatus.ACTIVE),
                notes=client_fields.get("notes"),
                created_by=client_fields.get("created_by"),
                deleted_at=client_fields.get("deleted_at"),
            )
            self.db.add(record)
            self.db.flush()
            client = SeededClient(
                id=record.id,
                legal_entity_id=legal_entity.id,
                full_name=legal_entity.official_name,
                id_number=legal_entity.id_number,
                id_number_type=legal_entity.id_number_type,
                entity_type=legal_entity.entity_type,
                phone=getattr(person, "phone", None),
                email=getattr(person, "email", None),
                address_street=getattr(person, "address_street", None),
                address_building_number=getattr(person, "address_building_number", None),
                address_apartment=getattr(person, "address_apartment", None),
                address_city=getattr(person, "address_city", None),
                address_zip_code=getattr(person, "address_zip_code", None),
                office_client_number=record.office_client_number,
                notes=record.notes,
                vat_reporting_frequency=legal_entity.vat_reporting_frequency,
                vat_exempt_ceiling=legal_entity.vat_exempt_ceiling,
                advance_rate=legal_entity.advance_rate,
                advance_rate_updated_at=legal_entity.advance_rate_updated_at,
                accountant_id=record.accountant_id,
                status=record.status,
                created_by=record.created_by,
                deleted_at=record.deleted_at,
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


def _resolve_exclusive(one: Any, other: Any, *, names: str) -> None:
    if one is not None and other is not None:
        raise ValueError(f"Pass either {names}, not both")


def _sequence_period(sequence: int, *, start_year: int = 2026) -> str:
    year = start_year + (sequence - 1) // 12
    month = (sequence - 1) % 12 + 1
    return f"{year}-{month:02d}"


class BinderFactory:
    """Model-level Binder factory: no BinderService side effects (audit/timeline)."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        actor: User | None = None,
        created_by: int | None = None,
        binder_number: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        location_status: BinderLocationStatus = BinderLocationStatus.IN_OFFICE,
        capacity_status: BinderCapacityStatus = BinderCapacityStatus.OPEN,
        ready_for_handover_at: datetime | None = None,
        handed_over_at: date | None = None,
        handover_recipient_name: str | None = None,
        notes: str | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> Binder:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        _resolve_exclusive(actor, created_by, names="actor or created_by")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        if created_by is None:
            created_by = (
                actor.id
                if actor is not None
                else create_user(
                    self.db,
                    full_name=f"Binder Actor {sequence}",
                    email=f"binder-actor-{sequence}@example.com",
                ).id
            )
        binder = Binder(
            client_record_id=resolved_client_id,
            binder_number=binder_number or f"BIN-{sequence:04d}",
            period_start=period_start,
            period_end=period_end,
            location_status=location_status,
            capacity_status=capacity_status,
            ready_for_handover_at=ready_for_handover_at,
            handed_over_at=handed_over_at,
            handover_recipient_name=handover_recipient_name,
            notes=notes,
            created_by=created_by,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
        )
        self.db.add(binder)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(binder)
        return binder


class ChargeFactory:
    """Model-level Charge factory: no BillingService side effects (audit/timeline)."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        annual_report_id: int | None = None,
        charge_type: ChargeType = ChargeType.MONTHLY_RETAINER,
        status: ChargeStatus = ChargeStatus.DRAFT,
        amount: Decimal | int | str = Decimal("100.00"),
        period: str | None = None,
        months_covered: int = 1,
        description: str | None = None,
        created_by: int | None = None,
        issued_at: datetime | date | None = None,
        issued_by: int | None = None,
        paid_at: datetime | date | None = None,
        paid_by: int | None = None,
        canceled_at: datetime | date | None = None,
        canceled_by: int | None = None,
        cancellation_reason: str | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> Charge:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        _resolve_exclusive(business, business_id, names="business or business_id")
        next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        charge = Charge(
            client_record_id=resolved_client_id,
            business_id=business_id if business_id is not None else getattr(business, "id", None),
            annual_report_id=annual_report_id,
            charge_type=charge_type,
            status=status,
            amount=Decimal(str(amount)),
            period=period,
            months_covered=months_covered,
            description=description,
            created_by=created_by,
            issued_at=issued_at,
            issued_by=issued_by,
            paid_at=paid_at,
            paid_by=paid_by,
            canceled_at=canceled_at,
            canceled_by=canceled_by,
            cancellation_reason=cancellation_reason,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
        )
        self.db.add(charge)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(charge)
        return charge


class TaskFactory:
    """Model-level Task factory. Client stays unset unless the test asks for one."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus = TaskStatus.OPEN,
        priority: TaskPriority = TaskPriority.NORMAL,
        due_date: date | None = None,
        assigned_to: User | None = None,
        assigned_to_user_id: int | None = None,
        assigned_role: UserRole | None = None,
        source_domain: str | None = None,
        source_id: int | None = None,
        client: Any = None,
        client_record_id: int | None = None,
        action_key: str | None = None,
        action_payload: dict[str, Any] | None = None,
        created_by_user_id: int | None = None,
        completed_by_user_id: int | None = None,
        completed_at: datetime | None = None,
        canceled_by_user_id: int | None = None,
        canceled_at: datetime | None = None,
        deleted_at: datetime | None = None,
        commit: bool = False,
    ) -> Task:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        _resolve_exclusive(
            assigned_to, assigned_to_user_id, names="assigned_to or assigned_to_user_id"
        )
        sequence = next(self._sequence)
        task = Task(
            title=title or f"Test Task {sequence}",
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            assigned_to_user_id=(
                assigned_to_user_id
                if assigned_to_user_id is not None
                else getattr(assigned_to, "id", None)
            ),
            assigned_role=assigned_role,
            source_domain=source_domain,
            source_id=source_id,
            client_record_id=(
                client_record_id if client_record_id is not None else getattr(client, "id", None)
            ),
            action_key=action_key,
            action_payload=action_payload,
            created_by_user_id=created_by_user_id,
            completed_by_user_id=completed_by_user_id,
            completed_at=completed_at,
            canceled_by_user_id=canceled_by_user_id,
            canceled_at=canceled_at,
            deleted_at=deleted_at,
        )
        self.db.add(task)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(task)
        return task


class TaxCalendarEntryFactory:
    """Model-level TaxCalendarEntry factory."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._sequence = count(1)

    def __call__(
        self,
        *,
        obligation_type: ObligationType = ObligationType.VAT,
        period: str | None = None,
        period_months_count: int | None = None,
        tax_year: int = 2026,
        due_date: date = date(2026, 2, 15),
        deadline_rule_id: int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        commit: bool = False,
    ) -> TaxCalendarEntry:
        sequence = next(self._sequence)
        if obligation_type == ObligationType.ANNUAL_REPORT:
            resolved_period = None
            resolved_months_count = None
            rule_type = DeadlineRuleType.ANNUAL_REPORT
        else:
            resolved_period = period or _sequence_period(sequence, start_year=tax_year)
            resolved_months_count = period_months_count or 1
            rule_type = (
                DeadlineRuleType.VAT_BIMONTHLY
                if obligation_type == ObligationType.VAT and resolved_months_count == 2
                else DeadlineRuleType.VAT_MONTHLY
                if obligation_type == ObligationType.VAT
                else DeadlineRuleType.ADVANCE_BIMONTHLY
                if resolved_months_count == 2
                else DeadlineRuleType.ADVANCE_MONTHLY
            )
        if deadline_rule_id is None:
            deadline_rule_id = self.db.scalar(
                select(DeadlineRule.id)
                .where(DeadlineRule.rule_type == rule_type)
                .order_by(DeadlineRule.effective_from.desc())
                .limit(1)
            )
        if deadline_rule_id is None:
            raise ValueError(f"No DeadlineRule exists for {rule_type.value}")
        entry_fields: dict[str, Any] = {
            "obligation_type": obligation_type,
            "period": resolved_period,
            "period_months_count": resolved_months_count,
            "tax_year": tax_year,
            "due_date": due_date,
            "deadline_rule_id": deadline_rule_id,
            "updated_at": updated_at,
        }
        if created_at is not None:
            entry_fields["created_at"] = created_at
        entry = TaxCalendarEntry(**entry_fields)
        self.db.add(entry)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(entry)
        return entry


class AdvancePaymentFactory:
    """Model-level AdvancePayment factory."""

    def __init__(
        self,
        db: Session,
        client_factory: ClientFactory,
        tax_calendar_entry_factory: TaxCalendarEntryFactory,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.tax_calendar_entry_factory = tax_calendar_entry_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        period: str | None = None,
        period_months_count: int = 1,
        due_date: date = date(2026, 2, 15),
        due_date_original: date | None = None,
        due_date_effective: date | None = None,
        due_date_override_reason: str | None = None,
        expected_amount: Decimal | int | str = Decimal("0.00"),
        paid_amount: Decimal | int | str = Decimal("0.00"),
        turnover_amount: Decimal | int | str | None = None,
        advance_rate: Decimal | int | str | None = None,
        calculated_amount: Decimal | int | str = Decimal("0.00"),
        override_amount: Decimal | int | str | None = None,
        withheld_amount: Decimal | int | str | None = None,
        turnover_source: TurnoverSource | None = None,
        turnover_snapshot_at: datetime | None = None,
        status: AdvancePaymentStatus = AdvancePaymentStatus.PENDING,
        paid_at: datetime | None = None,
        payment_method: PaymentMethod | None = None,
        payment_reference: str | None = None,
        annual_report_id: int | None = None,
        tax_calendar_entry_id: int | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        restored_at: datetime | None = None,
        restored_by: int | None = None,
        commit: bool = False,
    ) -> AdvancePayment:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        resolved_client_id = client_record_id if client_record_id is not None else client.id
        resolved_period = period or _sequence_period(sequence)
        if tax_calendar_entry_id is None:
            entry = self.tax_calendar_entry_factory(
                obligation_type=ObligationType.ADVANCE_PAYMENT,
                period=resolved_period,
                period_months_count=period_months_count,
                tax_year=int(resolved_period[:4]),
                due_date=due_date,
            )
            tax_calendar_entry_id = entry.id
        payment_fields: dict[str, Any] = {
            "client_record_id": resolved_client_id,
            "period": resolved_period,
            "period_months_count": period_months_count,
            "due_date": due_date,
            "due_date_original": due_date_original,
            "due_date_effective": due_date_effective,
            "due_date_override_reason": due_date_override_reason,
            "expected_amount": Decimal(str(expected_amount)),
            "paid_amount": Decimal(str(paid_amount)),
            "turnover_amount": None if turnover_amount is None else Decimal(str(turnover_amount)),
            "advance_rate": None if advance_rate is None else Decimal(str(advance_rate)),
            "calculated_amount": Decimal(str(calculated_amount)),
            "override_amount": None if override_amount is None else Decimal(str(override_amount)),
            "withheld_amount": None if withheld_amount is None else Decimal(str(withheld_amount)),
            "turnover_source": turnover_source,
            "turnover_snapshot_at": turnover_snapshot_at,
            "status": status,
            "paid_at": paid_at,
            "payment_method": payment_method,
            "payment_reference": payment_reference,
            "annual_report_id": annual_report_id,
            "tax_calendar_entry_id": tax_calendar_entry_id,
            "notes": notes,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
            "restored_at": restored_at,
            "restored_by": restored_by,
        }
        if created_at is not None:
            payment_fields["created_at"] = created_at
        payment = AdvancePayment(**payment_fields)
        self.db.add(payment)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(payment)
        return payment


class PermanentDocumentFactory:
    """Model-level PermanentDocument factory."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        scope: DocumentScope = DocumentScope.CLIENT,
        document_type: PermanentDocumentType = PermanentDocumentType.ID_COPY,
        storage_key: str | None = None,
        original_filename: str | None = None,
        file_size_bytes: int | None = None,
        mime_type: str | None = None,
        tax_year: int | None = None,
        is_present: bool = True,
        is_deleted: bool = False,
        status: DocumentStatus = DocumentStatus.PENDING,
        version: int = 1,
        superseded_by: int | None = None,
        annual_report_id: int | None = None,
        binder_id: int | None = None,
        uploaded_by: int | None = None,
        uploaded_at: datetime | None = None,
        approved_by: int | None = None,
        approved_at: datetime | None = None,
        rejected_by: int | None = None,
        rejected_at: datetime | None = None,
        commit: bool = False,
    ) -> PermanentDocument:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        _resolve_exclusive(business, business_id, names="business or business_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        if uploaded_by is None:
            uploaded_by = create_user(
                self.db,
                full_name=f"Document Uploader {sequence}",
                email=f"document-uploader-{sequence}@example.com",
            ).id
        document_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "scope": scope,
            "document_type": document_type,
            "storage_key": storage_key or f"test/documents/{sequence}.pdf",
            "original_filename": original_filename,
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type,
            "tax_year": tax_year,
            "is_present": is_present,
            "is_deleted": is_deleted,
            "status": status,
            "version": version,
            "superseded_by": superseded_by,
            "annual_report_id": annual_report_id,
            "binder_id": binder_id,
            "uploaded_by": uploaded_by,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "rejected_by": rejected_by,
            "rejected_at": rejected_at,
        }
        if uploaded_at is not None:
            document_fields["uploaded_at"] = uploaded_at
        document = PermanentDocument(**document_fields)
        self.db.add(document)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(document)
        return document


class SignatureRequestFactory:
    """Model-level SignatureRequest factory."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        created_by: int | None = None,
        annual_report_id: int | None = None,
        document_id: int | None = None,
        request_type: SignatureRequestType = SignatureRequestType.CUSTOM,
        title: str | None = None,
        description: str | None = None,
        content_hash: str | None = None,
        storage_key: str | None = None,
        signer_name: str = "Test Signer",
        signer_email: str | None = None,
        signer_phone: str | None = None,
        status: SignatureRequestStatus = SignatureRequestStatus.PENDING_SIGNATURE,
        signing_token: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        sent_at: datetime | None = None,
        expires_at: datetime | None = None,
        expiry_days: int = 14,
        signed_at: datetime | None = None,
        declined_at: datetime | None = None,
        canceled_at: datetime | None = None,
        canceled_by: int | None = None,
        signer_ip_address: str | None = None,
        signer_user_agent: str | None = None,
        decline_reason: str | None = None,
        signed_document_key: str | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> SignatureRequest:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        _resolve_exclusive(business, business_id, names="business or business_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        if created_by is None:
            created_by = create_user(
                self.db,
                full_name=f"Signature Actor {sequence}",
                email=f"signature-actor-{sequence}@example.com",
            ).id
        request_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "created_by": created_by,
            "annual_report_id": annual_report_id,
            "document_id": document_id,
            "request_type": request_type,
            "title": title or f"Test Signature Request {sequence}",
            "description": description,
            "content_hash": content_hash,
            "storage_key": storage_key,
            "signer_name": signer_name,
            "signer_email": signer_email,
            "signer_phone": signer_phone,
            "status": status,
            "signing_token": signing_token,
            "updated_at": updated_at,
            "sent_at": sent_at,
            "expires_at": expires_at,
            "expiry_days": expiry_days,
            "signed_at": signed_at,
            "declined_at": declined_at,
            "canceled_at": canceled_at,
            "canceled_by": canceled_by,
            "signer_ip_address": signer_ip_address,
            "signer_user_agent": signer_user_agent,
            "decline_reason": decline_reason,
            "signed_document_key": signed_document_key,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            request_fields["created_at"] = created_at
        request = SignatureRequest(**request_fields)
        self.db.add(request)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(request)
        return request


class NotificationFactory:
    """Model-level Notification factory."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        business: Business | None = None,
        business_id: int | None = None,
        binder_id: int | None = None,
        annual_report_id: int | None = None,
        signature_request_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        trigger: NotificationTrigger = NotificationTrigger.CLIENT_GENERAL_MESSAGE,
        channel: NotificationChannel = NotificationChannel.EMAIL,
        recipient: str | None = None,
        content_snapshot: str = "Test notification",
        subject_snapshot: str | None = None,
        status: NotificationStatus = NotificationStatus.PENDING,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
        error_message: str | None = None,
        retry_count: int = 0,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
        triggered_by: int | None = None,
        created_at: datetime | None = None,
        commit: bool = False,
    ) -> Notification:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        _resolve_exclusive(business, business_id, names="business or business_id")
        next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        notification_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "business_id": business_id
            if business_id is not None
            else getattr(business, "id", None),
            "binder_id": binder_id,
            "annual_report_id": annual_report_id,
            "signature_request_id": signature_request_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "trigger": trigger,
            "channel": channel,
            "recipient": recipient,
            "content_snapshot": content_snapshot,
            "subject_snapshot": subject_snapshot,
            "status": status,
            "sent_at": sent_at,
            "failed_at": failed_at,
            "error_message": error_message,
            "retry_count": retry_count,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "triggered_by": triggered_by,
        }
        if created_at is not None:
            notification_fields["created_at"] = created_at
        notification = Notification(**notification_fields)
        self.db.add(notification)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(notification)
        return notification


class VatWorkItemFactory:
    """Model-level VatWorkItem factory."""

    def __init__(
        self,
        db: Session,
        client_factory: ClientFactory,
        tax_calendar_entry_factory: TaxCalendarEntryFactory,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.tax_calendar_entry_factory = tax_calendar_entry_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        created_by: int | None = None,
        assigned_to: int | None = None,
        period: str | None = None,
        period_type: VatType = VatType.MONTHLY,
        status: VatWorkItemStatus = VatWorkItemStatus.MATERIAL_RECEIVED,
        pending_materials_note: str | None = None,
        total_output_vat: Decimal | int | str = Decimal("0.00"),
        total_input_vat: Decimal | int | str = Decimal("0.00"),
        net_vat: Decimal | int | str = Decimal("0.00"),
        total_output_net: Decimal | int | str = Decimal("0.00"),
        total_input_net: Decimal | int | str = Decimal("0.00"),
        final_vat_amount: Decimal | int | str | None = None,
        is_overridden: bool = False,
        override_justification: str | None = None,
        submission_method: SubmissionMethod | None = None,
        filed_at: datetime | None = None,
        filed_by: int | None = None,
        submission_reference: str | None = None,
        is_amendment: bool = False,
        amends_item_id: int | None = None,
        tax_calendar_entry_id: int | None = None,
        due_date_original: date | None = None,
        due_date_effective: date | None = None,
        due_date_override_reason: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> VatWorkItem:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        if created_by is None:
            created_by = create_user(
                self.db,
                full_name=f"VAT Actor {sequence}",
                email=f"vat-actor-{sequence}@example.com",
            ).id
        resolved_period = period or _sequence_period(sequence)
        months_count = 2 if period_type == VatType.BIMONTHLY else 1
        if tax_calendar_entry_id is None:
            entry = self.tax_calendar_entry_factory(
                obligation_type=ObligationType.VAT,
                period=resolved_period,
                period_months_count=months_count,
                tax_year=int(resolved_period[:4]),
                due_date=due_date_original or date(2026, 2, 15),
            )
            tax_calendar_entry_id = entry.id
            due_date_original = entry.due_date
        work_item_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "created_by": created_by,
            "assigned_to": assigned_to,
            "period": resolved_period,
            "period_type": period_type,
            "status": status,
            "pending_materials_note": pending_materials_note,
            "total_output_vat": Decimal(str(total_output_vat)),
            "total_input_vat": Decimal(str(total_input_vat)),
            "net_vat": Decimal(str(net_vat)),
            "total_output_net": Decimal(str(total_output_net)),
            "total_input_net": Decimal(str(total_input_net)),
            "final_vat_amount": None
            if final_vat_amount is None
            else Decimal(str(final_vat_amount)),
            "is_overridden": is_overridden,
            "override_justification": override_justification,
            "submission_method": submission_method,
            "filed_at": filed_at,
            "filed_by": filed_by,
            "submission_reference": submission_reference,
            "is_amendment": is_amendment,
            "amends_item_id": amends_item_id,
            "tax_calendar_entry_id": tax_calendar_entry_id,
            "due_date_original": due_date_original,
            "due_date_effective": due_date_effective,
            "due_date_override_reason": due_date_override_reason,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            work_item_fields["created_at"] = created_at
        if updated_at is not None:
            work_item_fields["updated_at"] = updated_at
        work_item = VatWorkItem(**work_item_fields)
        self.db.add(work_item)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(work_item)
        return work_item


class AuthorityContactFactory:
    """Model-level AuthorityContact factory."""

    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._sequence = count(1)

    def __call__(
        self,
        *,
        client: Any = None,
        client_record_id: int | None = None,
        contact_type: ContactType = ContactType.OTHER,
        name: str | None = None,
        office: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        deleted_at: datetime | None = None,
        deleted_by: int | None = None,
        commit: bool = False,
    ) -> AuthorityContact:
        _resolve_exclusive(client, client_record_id, names="client or client_record_id")
        sequence = next(self._sequence)
        if client is None and client_record_id is None:
            client = self.client_factory()
        contact_fields: dict[str, Any] = {
            "client_record_id": (client_record_id if client_record_id is not None else client.id),
            "contact_type": contact_type,
            "name": name or f"Test Authority Contact {sequence}",
            "office": office,
            "phone": phone,
            "email": email,
            "notes": notes,
            "updated_at": updated_at,
            "deleted_at": deleted_at,
            "deleted_by": deleted_by,
        }
        if created_at is not None:
            contact_fields["created_at"] = created_at
        contact = AuthorityContact(**contact_fields)
        self.db.add(contact)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(contact)
        return contact


class AnnualReportFactory:
    def __init__(self, db: Session, client_factory: ClientFactory) -> None:
        self.db = db
        self.client_factory = client_factory
        self._actor_sequence = count(1)

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
        if actor is not None:
            resolved_actor_id = actor.id
            resolved_actor_name = created_by_name or actor.full_name
        elif created_by is not None:
            resolved_actor_id = created_by
            resolved_actor_name = created_by_name or "Test Actor"
        else:
            actor_sequence = next(self._actor_sequence)
            actor = create_user(
                self.db,
                full_name=f"Annual Report Actor {actor_sequence}",
                email=f"annual-report-actor-{actor_sequence}@example.com",
            )
            resolved_actor_id = actor.id
            resolved_actor_name = created_by_name or actor.full_name
        return AnnualReportService(self.db).create_report(
            client_record_id=resolved_client_id,
            tax_year=tax_year,
            client_type=client_type,
            created_by=resolved_actor_id,
            created_by_name=resolved_actor_name,
            deadline_type=deadline_type,
            **report_fields,
        )
