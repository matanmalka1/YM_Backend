from types import SimpleNamespace

from app.audit.audit_constants import (
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BINDER,
)
from app.dashboard.services.dashboard_recent_activity_service import (
    _ACTIVITY_TYPES,
    RecentActivityService,
)


def _label_for(action: str, note: str | None, entity_type: str = ENTITY_ANNUAL_REPORT) -> str:
    # _label only reads `row`; build the service without touching the DB.
    service = RecentActivityService.__new__(RecentActivityService)
    row = SimpleNamespace(action=action, entity_type=entity_type, note=note)
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


def test_binder_label_uses_action_not_note():
    # Binder lifecycle notes are operational reason strings (e.g. "נמסר ללקוח"); the
    # dashboard must show the lifecycle-action label, never the raw note.
    assert (
        _label_for(ACTION_BINDER_MARKED_READY_FOR_HANDOVER, "סומן כמוכן למסירה", ENTITY_BINDER)
        == "קלסר מוכן למסירה"
    )
    assert _label_for(ACTION_BINDER_HANDED_OVER, "נמסר ללקוח", ENTITY_BINDER) == "קלסר נמסר ללקוח"


def test_binder_activity_type_marks_ready_and_handover_as_done():
    assert _ACTIVITY_TYPES[ACTION_BINDER_MARKED_READY_FOR_HANDOVER] == "done"
    assert _ACTIVITY_TYPES[ACTION_BINDER_HANDED_OVER] == "done"
