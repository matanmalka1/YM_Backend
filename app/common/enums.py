"""Shared enums used across multiple business domains."""

from enum import Enum as PyEnum


class SubmissionMethod(str, PyEnum):
    ONLINE = "online"  # שידור ישיר (מייצגים)
    MANUAL = "manual"  # הגשה פיזית לפקיד השומה
    REPRESENTATIVE = "representative"  # דרך מערכת המייצגים (שע"מ)


class VatType(str, PyEnum):
    """VAT reporting frequency for a legal entity (Client level)."""

    MONTHLY = "monthly"
    BIMONTHLY = "bimonthly"
    EXEMPT = "exempt"


class EntityType(str, PyEnum):
    """
    The legal/tax classification of a Client (legal entity).

    OSEK_PATUR  — עוסק פטור: exempt from VAT collection; annual reporting only.
    OSEK_MURSHE — עוסק מורשה: collects/deducts VAT; monthly or bi-monthly reporting.
    COMPANY_LTD — חברה בע"מ: separate legal entity with its own ח"פ; monthly/bi-monthly.
    EMPLOYEE    — שכיר: wage earner; no VAT reporting.
    """

    OSEK_PATUR = "osek_patur"
    OSEK_MURSHE = "osek_murshe"
    COMPANY_LTD = "company_ltd"
    EMPLOYEE = "employee"


class IdNumberType(str, PyEnum):
    INDIVIDUAL = "individual"  # ת"ז — 9 ספרות עם ספרת ביקורת
    CORPORATION = "corporation"  # ח"פ — 9 ספרות
    PASSPORT = "passport"  # דרכון — לתושבי חוץ
    OTHER = "other"


class AdvancePaymentFrequency(str, PyEnum):
    """Advance payment reporting frequency — independent from VAT frequency."""

    MONTHLY = "monthly"
    BIMONTHLY = "bimonthly"


class ObligationType(str, PyEnum):
    """Regulatory obligation category for TaxCalendarEntry.

    NATIONAL_INSURANCE is reserved but not yet wired to a DeadlineRuleType
    (intentionally unsupported in PR 1 of the tax-calendar foundation).
    """

    VAT = "vat"
    ADVANCE_PAYMENT = "advance_payment"
    ANNUAL_REPORT = "annual_report"
    NATIONAL_INSURANCE = "national_insurance"


class ObligationStatus(str, PyEnum):
    """The lifecycle every tax obligation runs, whatever its type.

    VAT, advance payments and annual reports are three views of one thing: a client
    owes an obligation for a period, works it through, and settles it by a deadline.
    They previously ran this sequence under three different names, with three
    transition tables, because they were written separately and never compared.

    Stage order is the declaration order, and it is load-bearing — the transition
    graph reads it (``app/common/obligation_lifecycle.py``). ``CANCELED`` sits off
    the ladder: it is reachable from any unlocked stage and has no position on it.

    An obligation that exists is by definition waiting for its inputs, so there is
    no separate "not started" stage. What counts as the input differs by type — the
    client's documents for VAT, the filed VAT return for an advance, the year's
    material for an annual report — but the stage is the same.
    """

    AWAITING_INPUT = "awaiting_input"  # ממתין לחומר
    INPUT_RECEIVED = "input_received"  # החומר התקבל
    IN_PROGRESS = "in_progress"  # בעבודה
    AWAITING_VERIFICATION = "awaiting_verification"  # ממתין לאימות
    SUBMITTED = "submitted"  # הוגש
    CANCELED = "canceled"  # בוטל


# One definition of "this obligation needs no further work", shared by the Python
# predicate below and every SQL query asking the same question. Per-domain resolved
# sets used to answer this three times, and VAT's disagreed with its own SQL.
RESOLVED_OBLIGATION_STATUSES: frozenset[ObligationStatus] = frozenset(
    {
        ObligationStatus.SUBMITTED,
        ObligationStatus.CANCELED,
    }
)


def is_obligation_resolved(status: ObligationStatus) -> bool:
    """Whether an obligation needs no further work.

    Includes CANCELED: a cancelled obligation is not outstanding work, even though
    it was never submitted.
    """
    return status in RESOLVED_OBLIGATION_STATUSES


class DeadlineRuleType(str, PyEnum):
    """Regulatory rule variant. Maps to one ObligationType."""

    VAT_MONTHLY = "vat_monthly"
    VAT_BIMONTHLY = "vat_bimonthly"
    ADVANCE_MONTHLY = "advance_monthly"
    ADVANCE_BIMONTHLY = "advance_bimonthly"
    ANNUAL_REPORT = "annual_report"


__all__ = [
    "RESOLVED_OBLIGATION_STATUSES",
    "AdvancePaymentFrequency",
    "DeadlineRuleType",
    "EntityType",
    "IdNumberType",
    "ObligationStatus",
    "ObligationType",
    "SubmissionMethod",
    "VatType",
    "is_obligation_resolved",
]
