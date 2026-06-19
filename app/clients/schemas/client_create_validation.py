from app.clients.client_constants import (
    ADVANCE_PAYMENT_FREQUENCY_REQUIRED_ERROR,
    COMPANY_EXEMPT_VAT_ERROR,
    CONFLICTING_ID_NUMBER_TYPE_ERROR,
    EDIT_VAT_EXEMPT_CEILING_ERROR,
    NON_PATUR_VAT_EXEMPT_CEILING_ERROR,
    PATUR_MANUAL_VAT_FREQUENCY_ERROR,
    SUPPORTED_CREATE_ENTITY_TYPES,
    SYSTEM_VAT_EXEMPT_CEILING_ERROR,
    UNSUPPORTED_EMPLOYEE_CREATE_ERROR,
    VAT_FREQUENCY_REQUIRED_ERROR,
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
