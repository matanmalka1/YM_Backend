from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.audit_constants import ENTITY_CLIENT
from app.audit.services.audit_entity_audit_writer import EntityAuditWriter
from app.businesses.models.business import Business
from app.businesses.services.business_service import BusinessService
from app.businesses.services.business_client_business_service import ClientBusinessService
from app.clients.client_constants import (
    COMPANY_CORPORATION_ID_ERROR,
    UNSUPPORTED_EMPLOYEE_CREATE_ERROR,
)
from app.clients.client_create_policy import (
    derive_id_number_type,
    normalize_vat_exempt_ceiling,
    normalize_vat_reporting_frequency,
    preview_vat_reporting_frequency,
)
from app.clients.models.client_record import ClientRecord
from app.clients.repositories.client_record_repository import ClientRecordRepository
from app.clients.schemas.client import (
    ClientOnboardingRequest,
)
from app.clients.schemas.client_record_response import CreateClientRecordResponse
from app.clients.services.client_onboarding_orchestrator import (
    ClientOnboardingOrchestrator,
)
from app.clients.services.client_query_service import ClientQueryService
from app.clients.services.client_impact_preview_service import compute_creation_impact
from app.clients.client_messages import (
    CLIENT_ID_NUMBER_DELETED,
    CLIENT_ID_NUMBER_EXISTS,
)
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppError, ConflictError
from app.legal_entities.repositories.legal_entity_repository import LegalEntityRepository
from app.legal_entities.repositories.person_repository import PersonRepository
from app.users.models.user import UserRole


class CreateClientService:
    """Coordinate creation of a reporting entity and its first business."""

    def __init__(self, db: Session):
        self.db = db
        self.record_repo = ClientRecordRepository(db)
        self.legal_entity_repo = LegalEntityRepository(db)
        self.person_repo = PersonRepository(db)
        self._audit = EntityAuditWriter(db)
        self.client_query_service = ClientQueryService(db)
        self.business_service = BusinessService(db)

    def create_client(
        self,
        *,
        full_name: str,
        id_number: str,
        business_name: str | None = None,
        id_number_type: IdNumberType = IdNumberType.INDIVIDUAL,  # type: ignore
        entity_type: EntityType | None = None,
        phone: str | None = None,
        email: str | None = None,
        address_street: str | None = None,
        address_building_number: str | None = None,
        address_apartment: str | None = None,
        address_city: str | None = None,
        address_zip_code: str | None = None,
        vat_reporting_frequency: VatType | None = None,
        advance_payment_frequency: AdvancePaymentFrequency | None = None,
        vat_exempt_ceiling=None,
        advance_rate=None,
        accountant_id: int | None = None,
        business_opened_at: date | None = None,
        business_notes: str | None = None,
        actor_id: int | None = None,
        reference_date: date | None = None,
    ) -> tuple[ClientRecord, Business]:
        """
        Create all records in the current DB transaction.

        The caller/session owner is responsible for commit. If any creation step
        raises, the request-level DB dependency rolls back all records.
        """
        normalized_business_name = (business_name or "").strip() or full_name.strip()
        if entity_type == EntityType.EMPLOYEE:
            raise ValueError(UNSUPPORTED_EMPLOYEE_CREATE_ERROR)

        try:
            client_record = self._create_client_identity(
                full_name=full_name,
                id_number=id_number,
                id_number_type=id_number_type,
                entity_type=entity_type,
                phone=phone,
                email=email,
                address_street=address_street,
                address_building_number=address_building_number,
                address_apartment=address_apartment,
                address_city=address_city,
                address_zip_code=address_zip_code,
                vat_reporting_frequency=vat_reporting_frequency,
                advance_payment_frequency=advance_payment_frequency,
                vat_exempt_ceiling=vat_exempt_ceiling,
                advance_rate=advance_rate,
                accountant_id=accountant_id,
                actor_id=actor_id,
                reference_date=reference_date,
            )
        except ConflictError as exc:
            if exc.code not in {ErrorCode.CLIENT_CONFLICT, ErrorCode.CLIENT_DELETED_EXISTS}:
                raise
            conflict = self.client_query_service.get_conflict_info(id_number)
            raise AppError(
                exc.message,
                exc.code,
                status_code=409,
                details={"conflict": conflict.model_dump(mode="json")},
            ) from exc
        business = self.business_service.create_business_for_client_record(
            client_record_id=client_record.id,
            opened_at=business_opened_at,
            business_name=normalized_business_name,
            notes=business_notes,
            actor_id=actor_id,
        )
        return client_record, business

    def _create_client_identity(
        self,
        *,
        full_name: str,
        id_number: str,
        id_number_type: IdNumberType = IdNumberType.INDIVIDUAL,  # type: ignore
        entity_type: EntityType | None = None,
        phone: str | None = None,
        email: str | None = None,
        address_street: str | None = None,
        address_building_number: str | None = None,
        address_apartment: str | None = None,
        address_city: str | None = None,
        address_zip_code: str | None = None,
        vat_reporting_frequency: VatType | None = None,
        advance_payment_frequency: AdvancePaymentFrequency | None = None,
        vat_exempt_ceiling=None,
        advance_rate=None,
        accountant_id: int | None = None,
        actor_id: int | None = None,
        reference_date: date | None = None,
    ) -> ClientRecord:
        if entity_type == EntityType.EMPLOYEE:
            raise ValueError(UNSUPPORTED_EMPLOYEE_CREATE_ERROR)
        if entity_type == EntityType.COMPANY_LTD and id_number_type != IdNumberType.CORPORATION:
            raise ValueError(COMPANY_CORPORATION_ID_ERROR)

        effective_vat_reporting_frequency = normalize_vat_reporting_frequency(
            entity_type, vat_reporting_frequency
        )
        effective_vat_exempt_ceiling = normalize_vat_exempt_ceiling(entity_type)

        if self.record_repo.get_active_by_id_number(id_number):
            raise ConflictError(
                CLIENT_ID_NUMBER_EXISTS.format(id_number=id_number), ErrorCode.CLIENT_CONFLICT
            )
        if self.record_repo.get_deleted_by_id_number(id_number):
            raise ConflictError(
                CLIENT_ID_NUMBER_DELETED.format(id_number=id_number),
                ErrorCode.CLIENT_DELETED_EXISTS,
            )
        if self.legal_entity_repo.get_by_id_number(id_number_type, id_number):
            raise ConflictError(
                CLIENT_ID_NUMBER_EXISTS.format(id_number=id_number), ErrorCode.CLIENT_CONFLICT
            )

        legal_entity = self.legal_entity_repo.create(
            id_number=id_number,
            id_number_type=id_number_type,
            official_name=full_name,
            entity_type=entity_type,
            vat_reporting_frequency=effective_vat_reporting_frequency,
            advance_payment_frequency=advance_payment_frequency,
            vat_exempt_ceiling=effective_vat_exempt_ceiling,
            advance_rate=advance_rate,
        )
        self.person_repo.ensure_owner(
            legal_entity_id=legal_entity.id,
            full_name=full_name,
            id_number=id_number,
            id_number_type=id_number_type,
            phone=phone,
            email=email,
            address_street=address_street,
            address_building_number=address_building_number,
            address_apartment=address_apartment,
            address_city=address_city,
            address_zip_code=address_zip_code,
        )
        try:
            client_record = self.record_repo.create(
                legal_entity_id=legal_entity.id,
                accountant_id=accountant_id,
                created_by=actor_id,
            )
        except IntegrityError as exc:
            raise ConflictError(
                CLIENT_ID_NUMBER_EXISTS.format(id_number=id_number), ErrorCode.CLIENT_CONFLICT
            ) from exc
        ClientOnboardingOrchestrator(self.db).run(
            client_record.id,
            actor_id=actor_id,
            entity_type=entity_type,
            reference_date=reference_date,
        )
        self._audit.record_create(
            ENTITY_CLIENT,
            client_record.id,
            actor_id,
            new_value={
                "full_name": full_name,
                "id_number": id_number,
                "entity_type": entity_type,
                "office_client_number": client_record.office_client_number,
            },
        )
        return client_record

    def create_from_request(
        self,
        request: ClientOnboardingRequest,
        *,
        actor_id: int,
        actor_role: UserRole,
    ) -> CreateClientRecordResponse:
        client_record, business = self.create_client(
            full_name=request.client.full_name,
            id_number=request.client.id_number,
            id_number_type=derive_id_number_type(request.client.entity_type),
            entity_type=request.client.entity_type,
            phone=request.client.phone,
            email=str(request.client.email) if request.client.email else None,
            address_street=request.client.address_street,
            address_building_number=request.client.address_building_number,
            address_apartment=request.client.address_apartment,
            address_city=request.client.address_city,
            address_zip_code=request.client.address_zip_code,
            vat_reporting_frequency=request.client.vat_reporting_frequency,
            advance_payment_frequency=request.client.advance_payment_frequency,
            vat_exempt_ceiling=request.client.vat_exempt_ceiling,
            advance_rate=request.client.advance_rate,
            accountant_id=request.client.accountant_id,
            business_name=request.business.business_name,
            business_opened_at=request.business.opened_at,
            business_notes=request.business.notes,
            actor_id=actor_id,
        )
        impact = compute_creation_impact(
            self.db,
            entity_type=request.client.entity_type,
            vat_reporting_frequency=preview_vat_reporting_frequency(
                request.client.entity_type,
                request.client.vat_reporting_frequency,
            ),
            advance_payment_frequency=request.client.advance_payment_frequency,
        )
        return CreateClientRecordResponse(
            client_record_id=client_record.id,
            client=self.client_query_service.get_full_client(client_record.id),
            business=ClientBusinessService(self.db).to_response(
                business,
                client_id=client_record.id,
            ),
            impact=impact,
        )


def create_client_identity_only(db, **kwargs) -> ClientRecord:
    client_record, _ = CreateClientService(db).create_client(**kwargs)
    return client_record
