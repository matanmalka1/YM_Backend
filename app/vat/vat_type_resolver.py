"""Resolves the effective VAT reporting frequency for a client (legal entity)."""

from app.common.enums import EntityType, VatType


def resolve_effective_vat_type(client) -> VatType:
    """
    Determine the effective VAT reporting frequency for a client (legal entity).

    - OSEK_PATUR / EMPLOYEE: always EXEMPT — no VAT reporting.
    - OSEK_MURSHE / COMPANY_LTD: use client.vat_reporting_frequency.
      Falls back to MONTHLY when not yet configured (legacy default).
    - entity_type not set (NULL): falls back to vat_reporting_frequency or MONTHLY.
    """
    exempt_types = {EntityType.OSEK_PATUR, EntityType.EMPLOYEE}
    if client.entity_type in exempt_types:
        return VatType.EXEMPT
    return client.vat_reporting_frequency or VatType.MONTHLY
