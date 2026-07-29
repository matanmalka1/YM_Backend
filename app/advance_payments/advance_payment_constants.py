"""Advance payment domain constants."""

import os
from decimal import Decimal

from app.common.integrations.tax_rules_financials import get_vat_rate_percent
from app.utils.time_utils import israel_today


def _resolve_vat_rate() -> Decimal:
    pct = get_vat_rate_percent(israel_today().year)
    if pct is not None:
        return Decimal(str(pct)) / Decimal("100")
    return Decimal(os.getenv("ADVANCE_PAYMENT_VAT_RATE", "0.18"))


ADVANCE_PAYMENT_VAT_RATE: Decimal = _resolve_vat_rate()

# A bulk turnover refresh is meant to cover what one advisor sees on one client's
# screen — a year is 12 periods. The cap keeps a mistyped request from writing to
# (and auditing) an unbounded number of records.
MAX_BULK_REFRESH_PAYMENTS = 60

# Bulk mark-paid covers one due-date batch on the org list — at most the office's
# client count for one period. Same rationale as MAX_BULK_REFRESH_PAYMENTS.
MAX_BULK_MARK_PAID_PAYMENTS = 200

# Clients per chunk of an office-wide annual generation. The whole run cannot be
# one request: the frontend's HTTP timeout is 15s and the office has hundreds of
# clients, each costing up to 12 period materialisations plus inserts. The server
# owns this number — the client only repeats the call until there is no cursor
# left, so the batch size can be retuned here without touching the frontend.
BULK_GENERATE_CLIENT_CHUNK_SIZE = 25

# A stored turnover further than this from the period's current VAT figure is
# flagged as a mismatch. 1 ILS absorbs rounding; anything above it is a real
# disagreement the advisor should look at.
VAT_TURNOVER_MISMATCH_TOLERANCE = Decimal("1.00")

# Closing-gate issues (§4.1.8): what blocks an advance from being closed. Payment
# in full is deliberately NOT a gate — the advisor decides when a period is
# settled, and a part-paid period closes with an outstanding difference (D-16).
ADVANCE_PAYMENT_TURNOVER_UNKNOWN_ISSUE = "המחזור לתקופה אינו ידוע"
ADVANCE_PAYMENT_EXPECTED_NOT_COMPUTED_ISSUE = (
    "לא ניתן לגזור סכום מקדמה — חסר שיעור מקדמה או סכום ידני"
)
ADVANCE_PAYMENT_NOT_READY_TO_CLOSE = "לא ניתן לסגור את המקדמה: {issues}"
