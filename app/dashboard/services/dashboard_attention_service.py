from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.users.models.user import UserRole
from app.utils.time_utils import israel_today
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceType,
    WorkQueueUrgency,
)
from app.work_queue.items.common import load_client_profiles
from app.work_queue.services.work_queue_service import WorkQueueService

_ATTENTION_URGENCIES = frozenset(
    {
        WorkQueueUrgency.OVERDUE,
        WorkQueueUrgency.APPROACHING,
        WorkQueueUrgency.IMPORTANT,
    }
)

_URGENCY_ORDER = {
    WorkQueueUrgency.OVERDUE: 0,
    WorkQueueUrgency.APPROACHING: 1,
    WorkQueueUrgency.IMPORTANT: 2,
    WorkQueueUrgency.UPCOMING: 3,
}

# Display cap: dashboard attention widget shows at most _MAX_ITEMS rows.
_MAX_ITEMS = 7
# Fetch headroom: WorkQueueService.list_items already returns items sorted by
# urgency then due_date (DB-side urgency filtering is not possible — work-queue
# items are aggregated in-memory from multiple sources). We over-fetch so the
# _is_attention_eligible filter (drops items lacking a due_date) still leaves
# >= _MAX_ITEMS rows in the common case before trimming.
_ATTENTION_FETCH_PAGE_SIZE = 20


def _sort_key(item: WorkQueueItem) -> tuple:
    return (_URGENCY_ORDER.get(item.urgency, 9), item.due_date or date.max)


def _href(item: WorkQueueItem) -> str:
    st = item.source_type
    if st == WorkQueueSourceType.VAT_WORK_ITEM:
        return f"/tax/vat/{item.source_id}"
    if st == WorkQueueSourceType.ANNUAL_REPORT:
        return f"/tax/reports/{item.source_id}"
    if st == WorkQueueSourceType.ADVANCE_PAYMENT:
        return "/tax/advance-payments"
    if st == WorkQueueSourceType.CHARGE:
        return "/charges"
    if st == WorkQueueSourceType.BINDER:
        return "/binders"
    if st == WorkQueueSourceType.TASK:
        return "/tasks"
    return "/"


def _reason(item: WorkQueueItem) -> str | None:
    st = item.source_type
    metadata = item.metadata or {}
    if st == WorkQueueSourceType.VAT_WORK_ITEM:
        return "דוח מע״מ לא הוגש"
    if st == WorkQueueSourceType.ANNUAL_REPORT:
        return "דוח שנתי ממתין להגשה"
    if st == WorkQueueSourceType.ADVANCE_PAYMENT:
        remaining = metadata.get("remaining_amount")
        if remaining:
            return f"יתרה לתשלום: ₪{remaining}"
        return "מקדמה ממתינה לתשלום"
    if st == WorkQueueSourceType.CHARGE:
        return "חיוב שלא שולם"
    if st == WorkQueueSourceType.BINDER:
        return None  # label already contains the waiting duration
    if st == WorkQueueSourceType.TASK:
        return metadata.get("description") or "משימה פתוחה"
    return None


def _amount(item: WorkQueueItem) -> str | None:
    if item.source_type == WorkQueueSourceType.CHARGE:
        return (item.metadata or {}).get("amount")
    return None


def _to_attention_item(item: WorkQueueItem, today: date) -> dict:
    days_delta = (item.due_date - today).days if item.due_date is not None else 0
    return {
        "id": f"{item.source_type.value}:{item.source_id}",
        "source_type": item.source_type,
        "source_id": item.source_id,
        "title": item.title,
        "client_name": item.client_name,
        "due_date": item.due_date,
        "days_delta": days_delta,
        "reason": _reason(item),
        "amount": _amount(item),
        "urgency": item.urgency,
        "href": _href(item),
    }


def _is_attention_eligible(item: WorkQueueItem) -> bool:
    """Tasks require a due_date and must be in an attention urgency tier."""
    if item.source_type == WorkQueueSourceType.TASK:
        return item.due_date is not None and item.urgency in _ATTENTION_URGENCIES
    return True


class DashboardAttentionService:
    def __init__(self, db: Session):
        self.db = db

    def build(
        self,
        user_role: UserRole | None = None,
        reference_date: date | None = None,
    ) -> list[dict]:
        if user_role != UserRole.ADVISOR:
            return []
        today = reference_date or israel_today()
        attention_urgencies = list(_ATTENTION_URGENCIES)
        all_items = WorkQueueService(self.db).list_items(
            urgencies=attention_urgencies,
            page=1,
            page_size=_ATTENTION_FETCH_PAGE_SIZE,
            include_client_identity=False,
        )
        all_items = [i for i in all_items if _is_attention_eligible(i)]

        all_items.sort(key=_sort_key)
        selected = all_items[:_MAX_ITEMS]
        self._attach_client_names(selected)
        return [_to_attention_item(i, today) for i in selected]

    def _attach_client_names(self, items: list[WorkQueueItem]) -> None:
        profiles = load_client_profiles(
            self.db,
            [item.client_record_id for item in items if item.client_record_id is not None],
        )
        for item in items:
            if item.client_record_id is None:
                continue
            profile = profiles.get(item.client_record_id)
            if profile is not None:
                item.client_name = profile.name
