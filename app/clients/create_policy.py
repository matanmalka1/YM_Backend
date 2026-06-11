from decimal import Decimal

from app.common.enums import EntityType, IdNumberType, VatType
from app.core.api_types import ApiDecimal
from app.utils.time_utils import israel_today
from app.vat.integrations.tax_rules_financials import get_financial_value


def derive_id_number_type(entity_type: EntityType) -> IdNumberType:
    if entity_type == EntityType.COMPANY_LTD:
        return IdNumberType.CORPORATION
    if entity_type in {EntityType.OSEK_PATUR, EntityType.OSEK_MURSHE}:
        return IdNumberType.INDIVIDUAL
    raise ValueError("סוג ישות זה אינו נתמך בפתיחת לקוח")


def normalize_vat_reporting_frequency(
    entity_type: EntityType | None,
    vat_reporting_frequency: VatType | None,
) -> VatType | None:
    if entity_type == EntityType.OSEK_PATUR:
        return VatType.EXEMPT
    return vat_reporting_frequency


def normalize_vat_exempt_ceiling(
    entity_type: EntityType | None,
) -> ApiDecimal | None:
    if entity_type == EntityType.OSEK_PATUR:
        year = israel_today().year
        return Decimal(str(get_financial_value(year, "osek_patur_ceiling_ils").value))
    return None


def preview_vat_reporting_frequency(
    entity_type: EntityType | None,
    vat_reporting_frequency: VatType | None,
) -> VatType | None:
    if entity_type == EntityType.OSEK_PATUR:
        return None
    return vat_reporting_frequency
