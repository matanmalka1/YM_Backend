from types import SimpleNamespace

from app.audit.audit_constants import (
    ACTION_BINDER_HANDED_OVER,
    ACTION_BINDER_MARKED_READY_FOR_HANDOVER,
    ACTION_INCOME_ADDED,
    ACTION_INCOME_DELETED,
    ACTION_VAT_WORK_ITEM_CREATED,
    ENTITY_ANNUAL_REPORT,
    ENTITY_BINDER,
    ENTITY_VAT_WORK_ITEM,
)
from app.audit.models.audit_entity_audit_log import EntityAuditLog
from app.dashboard.services.dashboard_recent_activity_service import (
    _ACTION_LABELS,
    _ACTIVITY_TYPES,
    RecentActivityService,
)
from tests.helpers.identity import seed_client_identity


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


def test_recent_activity_uses_metadata_client_context_for_vat_rows(test_db, test_user):
    client = seed_client_identity(
        test_db,
        full_name="Dashboard VAT Client",
        id_number="DASH-VAT-001",
    )
    test_db.add_all(
        EntityAuditLog(
            entity_type=ENTITY_VAT_WORK_ITEM,
            entity_id=idx + 1,
            performed_by=test_user.id,
            actor_type="user",
            actor_display_name=test_user.full_name,
            action=ACTION_VAT_WORK_ITEM_CREATED,
            new_value={"status": "material_received", "period": f"2026-0{idx + 1}"},
            metadata_json={
                "client_record_id": client.id,
                "period": f"2026-0{idx + 1}",
                "tax_year": 2026,
            },
        )
        for idx in range(6)
    )
    test_db.commit()

    items = RecentActivityService(test_db).build()

    assert len(items) == 5
    assert {item["client_name"] for item in items} == {"Dashboard VAT Client"}
    assert all(item["label"] == "נוצר תיק מע״מ" for item in items)
    assert all(item["href"].startswith("/tax/vat/") for item in items)


# --- Phase 7: dashboard recent-activity is EntityAuditLog-only; lock the contract ---

# The locked activity_type union the frontend recent-activity item schema renders.
# A future action rename must not silently introduce a new value or drop a row to a
# generic fallback — both are caught here. (plan §14: activity_type/label set unchanged.)
_LOCKED_ACTIVITY_TYPES = frozenset({"created", "updated", "done", "charge"})


def test_activity_type_union_is_locked():
    assert set(_ACTIVITY_TYPES.values()) == _LOCKED_ACTIVITY_TYPES


def test_every_labeled_action_has_an_explicit_activity_type():
    # No action that the dashboard can label may fall through to the "updated"
    # default in _serialize — every labeled action declares its activity_type.
    missing = [action for action in _ACTION_LABELS if action not in _ACTIVITY_TYPES]
    assert missing == [], f"actions missing an explicit activity_type: {missing}"


def test_every_typed_action_has_a_label():
    # Symmetric guard: every action with an activity_type also has a display label,
    # so no typed action falls through to the generic "בוצעה פעולה ב..." fallback.
    missing = [action for action in _ACTIVITY_TYPES if action not in _ACTION_LABELS]
    assert missing == [], f"actions missing a display label: {missing}"
