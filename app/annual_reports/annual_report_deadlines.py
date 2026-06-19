from datetime import date, datetime

from app.annual_reports.models.annual_report_enums import ClientAnnualFilingType
from app.common.enums import SubmissionMethod

try:
    from tax_rules.obligations.annual_reports import ANNUAL_REPORT_RULES_V2
    from tax_rules.types import EntityType as _TaxEntityType

    _RULES_AVAILABLE = True
except ImportError:
    _RULES_AVAILABLE = False

# Maps app ClientAnnualFilingType → tax_rules EntityType (where a 1:1 mapping exists)
_FILING_TYPE_TO_ENTITY_TYPE: dict[ClientAnnualFilingType, str] = {
    ClientAnnualFilingType.INDIVIDUAL: "osek_patur",
    ClientAnnualFilingType.SELF_EMPLOYED: "osek_murshe",
    ClientAnnualFilingType.EXEMPT_DEALER: "osek_patur",
    ClientAnnualFilingType.PARTNERSHIP: "osek_murshe",
    ClientAnnualFilingType.CORPORATION: "company_ltd",
    # CONTROL_HOLDER and PUBLIC_INSTITUTION have no matching EntityType in tax_rules_config
}

# Types that always use corporate deadline (31.07) — registry has company_ltd only,
# but CONTROL_HOLDER and PUBLIC_INSTITUTION share that deadline.
_CORPORATE_DEADLINE_TYPES = {
    ClientAnnualFilingType.CORPORATION,
    ClientAnnualFilingType.PUBLIC_INSTITUTION,
    ClientAnnualFilingType.CONTROL_HOLDER,
}


def _rule_for_entity(entity_type_str: str):
    """Return the first non-attachment AnnualReportRule matching entity_type, or None."""
    if not _RULES_AVAILABLE:
        return None
    try:
        et = _TaxEntityType(entity_type_str)
    except ValueError:
        return None
    for rule in ANNUAL_REPORT_RULES_V2:
        if rule.is_attachment:
            continue
        if et in rule.scope.entity_types:
            return rule
    return None


def standard_deadline(
    tax_year: int,
    client_type: ClientAnnualFilingType | None = None,
    submission_method: SubmissionMethod | None = None,
) -> datetime:
    """Statutory standard deadline by filing profile.

    Consults tax_rules_config.ANNUAL_REPORT_RULES_V2 for tax-year-specific
    overrides (e.g. 2025 extensions). Falls back to hardcoded statutory dates
    when the registry has no rule for the filing type.
    """
    # ── Corporate / control holder / public institution ───────────────────────
    if client_type in _CORPORATE_DEADLINE_TYPES:
        entity_str = _FILING_TYPE_TO_ENTITY_TYPE.get(client_type)
        rule = _rule_for_entity(entity_str) if entity_str else None
        if rule:
            specific = rule.tax_year_specific_due_dates.get(tax_year)
            if specific:
                d = date.fromisoformat(specific)
                return datetime(d.year, d.month, d.day, 23, 59, 59)
            return datetime(tax_year + 1, rule.default_due_month, rule.default_due_day, 23, 59, 59)
        return datetime(tax_year + 1, 7, 31, 23, 59, 59)

    # ── Individuals / self-employed / partners / exempt dealers ───────────────
    entity_str = _FILING_TYPE_TO_ENTITY_TYPE.get(client_type) if client_type else None
    rule = _rule_for_entity(entity_str) if entity_str else None
    if rule:
        specific = rule.tax_year_specific_due_dates.get(tax_year)
        if specific:
            d = date.fromisoformat(specific)
            return datetime(d.year, d.month, d.day, 23, 59, 59)
        # Registry default is 31.05; online/representative filers get 30.06 per ITA rules
        if submission_method in {
            SubmissionMethod.ONLINE,
            SubmissionMethod.REPRESENTATIVE,
        }:
            return datetime(tax_year + 1, 6, 30, 23, 59, 59)
        return datetime(tax_year + 1, rule.default_due_month, rule.default_due_day, 23, 59, 59)

    # ── Fallback (no registry rule) ───────────────────────────────────────────
    if submission_method in {SubmissionMethod.ONLINE, SubmissionMethod.REPRESENTATIVE}:
        return datetime(tax_year + 1, 6, 30, 23, 59, 59)
    return datetime(tax_year + 1, 5, 29, 23, 59, 59)


def extended_deadline(tax_year: int) -> datetime:
    """January 31 two years after the tax year (for authorised reps)."""
    return datetime(tax_year + 2, 1, 31, 23, 59, 59)


__all__ = ["standard_deadline", "extended_deadline"]
