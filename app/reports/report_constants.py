from __future__ import annotations

import tempfile
from pathlib import Path

AGING_CHARGE_FETCH_LIMIT = 2000
VAT_STALE_PENDING_DAYS = 30

EXPORT_TEMP_DIR = Path(tempfile.gettempdir()) / "exports"
AGING_EXPORT_FILENAME_PREFIX = "aging_report"
AGING_EXPORT_HEADER_COLOR = "366092"

AGING_REPORT_TITLE = "Aging Report"
AGING_REPORT_HEADERS = [
    "שם לקוח",
    'סה"כ חוב',
    "שוטף (0-30)",
    "30-60 ימים",
    "60-90 ימים",
    "90+ ימים",
    "תאריך עתיק",
    "ימים",
]
