"""Pydantic schemas for VAT Invoice entities."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.core.api_types import ApiDecimal
from app.utils.id_validation import validate_israeli_id_checksum
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    InvoiceType,
    VatRateType,
)

MAX_INVOICE_NUMBER_LENGTH = 100
MAX_COUNTERPARTY_NAME_LENGTH = 255
MAX_COUNTERPARTY_ID_LENGTH = 32
ANONYMOUS_COUNTERPARTY_ID = "999999999"


def validate_counterparty_pair(
    counterparty_id: str | None,
    counterparty_id_type: CounterpartyIdType | None,
) -> None:
    """Validate a (counterparty_id, counterparty_id_type) pair.

    Raises ValueError if the pair is inconsistent. Used both by the request
    schema (on a single request) and by the update service (on the merged
    effective pair, so a partial PATCH cannot leave an invalid persisted state).
    """
    cid = counterparty_id
    cid_type = counterparty_id_type

    if cid is None and cid_type is None:
        return

    if cid_type in (CounterpartyIdType.IL_BUSINESS, CounterpartyIdType.IL_PERSONAL):
        if cid is None:
            raise ValueError("יש להזין מספר מזהה ישראלי כאשר סוג המזהה הוא ישראלי")
        if not cid.isdigit() or len(cid) != 9:
            raise ValueError('מספר עוסק / ת"ז ישראלי חייב להיות 9 ספרות')
        if not validate_israeli_id_checksum(cid):
            raise ValueError('מספר עוסק / ת"ז ישראלי אינו תקין')
        return

    if cid_type == CounterpartyIdType.FOREIGN:
        if cid is None:
            raise ValueError("כאשר סוג המזהה הוא זר, יש להזין את מספר המזהה של הצד הנגדי")
        return

    if cid_type == CounterpartyIdType.ANONYMOUS:
        if cid != ANONYMOUS_COUNTERPARTY_ID:
            raise ValueError('עבור מזהה אנונימי יש להזין "999999999"')


class VatInvoiceValidatorMixin(BaseModel):
    """Shared field validators for VAT invoice create and update schemas."""

    counterparty_id: str | None = None
    counterparty_id_type: CounterpartyIdType | None = None

    @field_validator("invoice_number", "counterparty_name", "counterparty_id", check_fields=False)
    @classmethod
    def normalize_optional_strings(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_counterparty_id(self) -> VatInvoiceValidatorMixin:
        validate_counterparty_pair(self.counterparty_id, self.counterparty_id_type)
        return self


class VatInvoiceCreateRequest(VatInvoiceValidatorMixin):
    invoice_type: InvoiceType
    business_activity_id: int | None = None
    invoice_number: str | None = Field(default=None, max_length=MAX_INVOICE_NUMBER_LENGTH)
    invoice_date: date | None = None  # Date — לא DateTime
    counterparty_name: str | None = Field(default=None, max_length=MAX_COUNTERPARTY_NAME_LENGTH)
    gross_amount: ApiDecimal
    counterparty_id: str | None = Field(default=None, max_length=MAX_COUNTERPARTY_ID_LENGTH)
    counterparty_id_type: CounterpartyIdType | None = None
    expense_category: ExpenseCategory | None = None
    rate_type: VatRateType = VatRateType.STANDARD
    document_type: DocumentType | None = None

    @field_validator("gross_amount")
    @classmethod
    def gross_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("הסכום הכולל חייב להיות חיובי")
        return v


class VatInvoiceResponse(BaseModel):
    id: int
    work_item_id: int
    business_activity_id: int | None = None
    invoice_type: InvoiceType
    document_type: DocumentType | None = None
    invoice_number: str
    invoice_date: date  # Date — לא DateTime
    counterparty_name: str
    counterparty_id: str | None = None
    counterparty_id_type: CounterpartyIdType | None = None  # קיים במודל
    net_amount: ApiDecimal
    vat_amount: ApiDecimal
    expense_category: ExpenseCategory | None = None
    rate_type: VatRateType
    deduction_rate: ApiDecimal
    is_exceptional: bool
    created_by: int
    created_at: date  # Date במודל
    # Non-null only on create response — True when annual turnover crosses 80% of OSEK PATUR ceiling
    ceiling_warning: bool = False

    @computed_field
    @property
    def gross_amount(self) -> ApiDecimal:
        return self.net_amount + self.vat_amount

    model_config = {"from_attributes": True}


class VatInvoiceListResponse(BaseModel):
    # Non-paginated bounded child collection (all invoices for one work item).
    # Envelope fields are populated for shape consistency, not real pagination:
    # total == len(items), page == 1, page_size == len(items).
    items: list[VatInvoiceResponse]
    total: int
    page: int
    page_size: int
