from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.businesses.schemas.business_schemas import BusinessResponse
from app.clients.client_enums import ClientStatus
from app.clients.schemas.client_impact import ClientCreationImpactResponse
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.core.api_types import ApiDateTime, ApiDecimal, PaginatedResponse

TurnoverSource = Literal["reported", "manual", "none"]


class AnnualTurnover(BaseModel):
    amount: ApiDecimal | None = None
    source: TurnoverSource
    year: int


class ClientRecordResponse(BaseModel):
    id: int  # ClientRecord.id
    full_name: str  # LegalEntity.official_name / owner Person.full_name
    id_number: str  # LegalEntity.id_number
    id_number_type: IdNumberType | None = None  # LegalEntity.id_number_type
    entity_type: EntityType | None = None  # LegalEntity.entity_type
    status: ClientStatus = ClientStatus.ACTIVE  # ClientRecord.status
    office_client_number: int | None = None  # ClientRecord.office_client_number
    accountant_id: int | None = None  # ClientRecord.accountant_id
    notes: str | None = None  # ClientRecord.notes
    # ── Tax reporting (LegalEntity) ───────────────────────────────────────────
    vat_reporting_frequency: VatType | None = None
    advance_payment_frequency: AdvancePaymentFrequency | None = None
    vat_exempt_ceiling: ApiDecimal | None = None
    advance_rate: ApiDecimal | None = None
    advance_rate_updated_at: date | None = None
    annual_revenue: ApiDecimal | None = None
    # ── Contact (Person via PersonLegalEntityLink OWNER) ──────────────────────
    phone: str | None = None
    email: str | None = None
    address_street: str | None = None
    address_building_number: str | None = None
    address_apartment: str | None = None
    address_city: str | None = None
    address_zip_code: str | None = None
    # ── Metadata ──────────────────────────────────────────────────────────────
    created_at: ApiDateTime | None = None  # ClientRecord.created_at
    updated_at: ApiDateTime | None = None  # ClientRecord.updated_at
    created_by: int | None = None  # ClientRecord.created_by
    # ── Enriched (set by API layer) ───────────────────────────────────────────
    active_binder_number: str | None = None
    annual_turnover: AnnualTurnover | None = None

    model_config = {"from_attributes": True}


class ClientRecordListItem(BaseModel):
    """Thin DTO for the clients list/table rows.

    Contains only fields rendered by the clients table (``ClientColumns``).
    Detail/profile fields (tax reporting config, address, contact extras,
    metadata, turnover) stay on ``ClientRecordResponse`` and are served by
    ``GET /clients/{id}``.
    """

    id: int
    full_name: str
    id_number: str
    entity_type: EntityType | None = None
    status: ClientStatus = ClientStatus.ACTIVE
    office_client_number: int | None = None
    phone: str | None = None
    email: str | None = None
    created_at: ApiDateTime | None = None
    # Enriched (set by API layer)
    active_binder_number: str | None = None

    model_config = {"from_attributes": True}


class ClientRecordListStats(BaseModel):
    osek_patur: int = 0
    osek_murshe: int = 0
    company_ltd: int = 0
    employee: int = 0


class ClientRecordListResponse(PaginatedResponse[ClientRecordListItem]):
    stats: ClientRecordListStats


class ClientSidebarItemResponse(BaseModel):
    id: int
    full_name: str
    office_client_number: int | None = None
    phone: str | None = None
    email: str | None = None
    entity_type: EntityType | None = None
    vat_reporting_frequency: VatType | None = None


class ClientSidebarListResponse(PaginatedResponse[ClientSidebarItemResponse]):
    pass


class CreateClientRecordResponse(BaseModel):
    client_record_id: int
    client: ClientRecordResponse
    business: BusinessResponse
    impact: ClientCreationImpactResponse
