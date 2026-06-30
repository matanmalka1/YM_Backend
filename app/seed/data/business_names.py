from __future__ import annotations

from random import Random

from app.common.enums import EntityType

from .demo_catalog import BUSINESS_CATALOG

SOLE_PROP_BRANDS = [
    "סטודיו אורן",
    "קליניקת נועם",
    "מרכז שביט",
    "מעבדת גל",
    "משרד תבור",
    "סדנת ירדן",
    "בית מלאכה הדר",
    "מרחב כרמל",
    "נקודת איזון",
    "מסלול ירוק",
    "קו מקצועי",
    "אפיק פתרונות",
]

SOLE_PROP_SECTORS = [
    "ייעוץ עסקי",
    "שירותי עיצוב",
    "טיפול ורווחה",
    "שיווק דיגיטלי",
    "ניהול פרויקטים",
    "הדרכה מקצועית",
    "פיתוח תוכנה",
    "שירותי חשמל",
    "צילום ומדיה",
    "תכנון פנים",
    "קוסמטיקה מתקדמת",
    "שירותי תרגום",
]

EMPLOYEE_INCOME_NAMES = [
    "תיק הכנסות שכיר - הייטק",
    "תיק הכנסות שכיר - הוראה",
    "תיק הכנסות שכיר - בריאות",
    "תיק הכנסות שכיר - ניהול",
    "תיק הכנסות שכיר - תעשייה",
    "תיק הכנסות שכיר - פיננסים",
    "תיק הכנסות שכיר - ציבורי",
    "תיק הכנסות שכיר - שירותים",
]

BRANCH_LABELS = [
    "צפון",
    "מרכז",
    "ירושלים",
    "שרון",
    "שפלה",
    "דרום",
    "חיפה",
    "תל אביב",
    "בקעה",
    "גליל",
]


def seed_business_name(
    *,
    client_full_name: str,
    entity_type: EntityType | None,
    business_index: int,
    serial: int,
    rng: Random,
    used_names: set[str],
) -> str:
    base_name = _base_name(entity_type, serial, rng)
    candidate = _with_branch(base_name, business_index)
    return _unique_name(candidate, client_full_name, serial, used_names)


def _base_name(entity_type: EntityType | None, serial: int, rng: Random) -> str:
    if entity_type == EntityType.COMPANY_LTD:
        return BUSINESS_CATALOG[(serial - 1) % len(BUSINESS_CATALOG)]
    if entity_type == EntityType.EMPLOYEE:
        return EMPLOYEE_INCOME_NAMES[(serial - 1) % len(EMPLOYEE_INCOME_NAMES)]

    brand = SOLE_PROP_BRANDS[(serial - 1) % len(SOLE_PROP_BRANDS)]
    sector = rng.choice(SOLE_PROP_SECTORS)
    return f"{brand} - {sector}"


def _with_branch(base_name: str, business_index: int) -> str:
    if business_index == 0:
        return base_name
    branch = BRANCH_LABELS[(business_index - 1) % len(BRANCH_LABELS)]
    return f"{base_name} - פעילות {branch}"


def _unique_name(candidate: str, client_full_name: str, serial: int, used_names: set[str]) -> str:
    forbidden = {
        client_full_name,
        f"{client_full_name} 1",
        f"{client_full_name} 2",
        f"{client_full_name} 3",
    }
    suffix = 1
    unique_candidate = candidate
    while unique_candidate in used_names or unique_candidate in forbidden:
        suffix += 1
        branch = BRANCH_LABELS[(serial + suffix) % len(BRANCH_LABELS)]
        unique_candidate = f"{candidate} - סניף {branch} {serial + suffix}"
    used_names.add(unique_candidate)
    return unique_candidate
