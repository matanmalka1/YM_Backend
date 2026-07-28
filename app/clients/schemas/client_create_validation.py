from datetime import date

from app.clients.client_constants import (
    ADVANCE_LIABILITY_RANGE_WITHOUT_FREQUENCY_ERROR,
    ADVANCE_PAYMENT_FREQUENCY_REQUIRED_ERROR,
    COMPANY_EXEMPT_VAT_ERROR,
    CONFLICTING_ID_NUMBER_TYPE_ERROR,
    EDIT_VAT_EXEMPT_CEILING_ERROR,
    LIABILITY_RANGE_INVERTED_ERROR,
    NON_PATUR_VAT_EXEMPT_CEILING_ERROR,
    PATUR_MANUAL_VAT_FREQUENCY_ERROR,
    SUPPORTED_CREATE_ENTITY_TYPES,
    SYSTEM_VAT_EXEMPT_CEILING_ERROR,
    UNSUPPORTED_EMPLOYEE_CREATE_ERROR,
    VAT_FREQUENCY_REQUIRED_ERROR,
    VAT_LIABILITY_RANGE_WITHOUT_REPORTING_ERROR,
)
from app.clients.client_create_policy import derive_id_number_type
from app.common.enums import AdvancePaymentFrequency, EntityType, IdNumberType, VatType
from app.utils.id_validation import validate_israeli_id_checksum


def validate_identifier_for_entity(entity_type: EntityType, id_number: str) -> None:
    if entity_type == EntityType.COMPANY_LTD:
        if not id_number.isdigit():
            raise ValueError("ח.פ חייב להכיל ספרות בלבד")
        if len(id_number) != 9:
            raise ValueError("ח.פ חייב להכיל בדיוק 9 ספרות")
        if not validate_israeli_id_checksum(id_number):
            raise ValueError("מספר ח.פ אינו תקין")
        return

    if not id_number.isdigit():
        raise ValueError("מספר תעודת זהות חייב להכיל ספרות בלבד")
    if len(id_number) != 9:
        raise ValueError("מספר תעודת זהות חייב להכיל בדיוק 9 ספרות")
    if not validate_israeli_id_checksum(id_number):
        raise ValueError("מספר תעודת זהות אינו תקין")


def validate_create_entity_rules(
    *,
    entity_type: EntityType | None,
    id_number: str,
    provided_id_number_type: IdNumberType | None,
    id_number_type_was_set: bool,
    vat_reporting_frequency: VatType | None,
    vat_reporting_frequency_was_set: bool,
    vat_exempt_ceiling_was_set: bool,
    advance_payment_frequency: AdvancePaymentFrequency | None = None,
) -> None:
    if entity_type is None:
        raise ValueError("יש לבחור סוג ישות")
    if entity_type == EntityType.EMPLOYEE:
        raise ValueError(UNSUPPORTED_EMPLOYEE_CREATE_ERROR)
    if entity_type not in SUPPORTED_CREATE_ENTITY_TYPES:
        raise ValueError("סוג ישות זה אינו נתמך בפתיחת לקוח")

    expected_id_number_type = derive_id_number_type(entity_type)
    if id_number_type_was_set and provided_id_number_type != expected_id_number_type:
        raise ValueError(CONFLICTING_ID_NUMBER_TYPE_ERROR)

    if entity_type == EntityType.OSEK_PATUR:
        if vat_reporting_frequency_was_set:
            raise ValueError(PATUR_MANUAL_VAT_FREQUENCY_ERROR)
        if vat_exempt_ceiling_was_set:
            raise ValueError(SYSTEM_VAT_EXEMPT_CEILING_ERROR)
    else:
        if vat_reporting_frequency is None:
            raise ValueError(VAT_FREQUENCY_REQUIRED_ERROR)
        if entity_type == EntityType.COMPANY_LTD and vat_reporting_frequency == VatType.EXEMPT:
            raise ValueError(COMPANY_EXEMPT_VAT_ERROR)
        if vat_exempt_ceiling_was_set:
            raise ValueError(NON_PATUR_VAT_EXEMPT_CEILING_ERROR)

    if advance_payment_frequency is None:
        raise ValueError(ADVANCE_PAYMENT_FREQUENCY_REQUIRED_ERROR)

    validate_identifier_for_entity(entity_type, id_number)


def validate_liability_ranges(
    *,
    vat_liable_from: date | None,
    vat_liable_to: date | None,
    advance_liable_from: date | None,
    advance_liable_to: date | None,
    annual_liable_from: date | None,
    annual_liable_to: date | None,
    vat_reporting_frequency: VatType | None = None,
    vat_reporting_frequency_known: bool = False,
    advance_payment_frequency: AdvancePaymentFrequency | None = None,
    advance_payment_frequency_known: bool = False,
) -> None:
    """A liability range must be orderable, and must belong to a type the client has.

    ``*_known`` says whether the caller can see the effective frequency. On update
    a frequency the request did not send is unknown here, so the "range without a
    configured type" check is skipped rather than guessed — the alternative is
    rejecting a valid edit because the request happened not to resend the field.
    """
    for start, end in (
        (vat_liable_from, vat_liable_to),
        (advance_liable_from, advance_liable_to),
        (annual_liable_from, annual_liable_to),
    ):
        if start is not None and end is not None and start > end:
            raise ValueError(LIABILITY_RANGE_INVERTED_ERROR)

    has_vat_range = vat_liable_from is not None or vat_liable_to is not None
    if (
        has_vat_range
        and vat_reporting_frequency_known
        and vat_reporting_frequency in (None, VatType.EXEMPT)
    ):
        raise ValueError(VAT_LIABILITY_RANGE_WITHOUT_REPORTING_ERROR)

    has_advance_range = advance_liable_from is not None or advance_liable_to is not None
    if has_advance_range and advance_payment_frequency_known and advance_payment_frequency is None:
        raise ValueError(ADVANCE_LIABILITY_RANGE_WITHOUT_FREQUENCY_ERROR)


def validate_update_entity_rules(
    *,
    vat_exempt_ceiling_was_set: bool,
) -> None:
    if vat_exempt_ceiling_was_set:
        raise ValueError(EDIT_VAT_EXEMPT_CEILING_ERROR)


def validate_preview_entity_rules(
    *,
    entity_type: EntityType,
    vat_reporting_frequency: VatType | None,
    vat_reporting_frequency_was_set: bool,
) -> None:
    if entity_type == EntityType.EMPLOYEE:
        raise ValueError(UNSUPPORTED_EMPLOYEE_CREATE_ERROR)
    if entity_type == EntityType.OSEK_PATUR:
        if vat_reporting_frequency_was_set and vat_reporting_frequency != VatType.EXEMPT:
            raise ValueError(PATUR_MANUAL_VAT_FREQUENCY_ERROR)
        return
    if entity_type == EntityType.COMPANY_LTD and vat_reporting_frequency == VatType.EXEMPT:
        raise ValueError(COMPANY_EXEMPT_VAT_ERROR)
    if vat_reporting_frequency is None:
        raise ValueError(VAT_FREQUENCY_REQUIRED_ERROR)
