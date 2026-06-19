from types import SimpleNamespace

from app.audit.audit_constants import (
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ENTITY_ANNUAL_REPORT,
)
from app.dashboard.services.dashboard_recent_activity_service import RecentActivityService


def _label_for(action: str, note: str | None) -> str:
    # _label only reads `row`; build the service without touching the DB.
    service = RecentActivityService.__new__(RecentActivityService)
    row = SimpleNamespace(action=action, entity_type=ENTITY_ANNUAL_REPORT, note=note)
    return service._label(row)


def test_label_never_leaks_keyvalue_metadata_note():
    # VAT import writes technical notes like "source=vat_import" — these must not surface.
    assert _label_for(ACTION_INCOME_ADDED, "source=vat_import") == "נוספה שורת הכנסה בדוח שנתי"
    assert (
        _label_for(ACTION_INCOME_DELETED, "mutation_source=vat_import; reason=force_replace")
        == "נמחקה שורת הכנסה בדוח שנתי"
    )


def test_label_uses_specific_text_for_income_expense_actions():
    # Previously these fell through to the generic "בוצעה פעולה בדוח שנתי".
    assert _label_for(ACTION_INCOME_ADDED, None) == "נוספה שורת הכנסה בדוח שנתי"


def test_label_keeps_genuine_free_text_note():
    assert _label_for(ACTION_INCOME_ADDED, "תיקון ידני לבקשת הלקוח") == "תיקון ידני לבקשת הלקוח"
