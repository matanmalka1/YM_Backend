"""Pydantic schema for VAT invoice update requests."""

from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator

from app.core.api_types import ApiDecimal
from app.vat.models.vat_enums import (
    CounterpartyIdType,
    DocumentType,
    ExpenseCategory,
    VatRateType,
)
from app.vat.schemas.vat_invoice_schema import (
    MAX_COUNTERPARTY_ID_LENGTH,
    MAX_COUNTERPARTY_NAME_LENGTH,
    MAX_INVOICE_NUMBER_LENGTH,
    VatInvoiceValidatorMixin,
)


class VatInvoiceUpdateRequest(VatInvoiceValidatorMixin):
    business_activity_id: int | None = None
    gross_amount: ApiDecimal | None = None
    invoice_number: str | None = Field(default=None, max_length=MAX_INVOICE_NUMBER_LENGTH)
    invoice_date: date | None = None  # Date — לא DateTime
    counterparty_name: str | None = Field(default=None, max_length=MAX_COUNTERPARTY_NAME_LENGTH)
    counterparty_id: str | None = Field(default=None, max_length=MAX_COUNTERPARTY_ID_LENGTH)
    counterparty_id_type: CounterpartyIdType | None = None
    expense_category: ExpenseCategory | None = None
    rate_type: VatRateType | None = None
    document_type: DocumentType | None = None

    @field_validator("gross_amount")
    @classmethod
    def gross_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("הסכום הכולל חייב להיות חיובי")
        return v
