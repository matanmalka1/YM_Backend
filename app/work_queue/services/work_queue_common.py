from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.clients.repositories.client_identity_repository import ClientIdentityRepository
from app.common.source_types import normalize_source_domain as normalize_source_domain
from app.common.source_types import source_route as source_route
from app.work_queue.schemas.work_queue import (
    WorkQueueItem,
    WorkQueueSourceSummary,
    WorkQueueSourceType,
    WorkQueueUrgency,
)

APPROACHING_DAYS = 7
IMPORTANT_DAYS = 21
UPCOMING_WINDOW_DAYS = 21

SOURCE_TYPE_LABELS = {
    WorkQueueSourceType.VAT_WORK_ITEM: 'דוח מע"מ',
    WorkQueueSourceType.ANNUAL_REPORT: "דוח שנתי",
    WorkQueueSourceType.ADVANCE_PAYMENT: "מקדמה",
    WorkQueueSourceType.CHARGE: "חיוב לא שולם",
    WorkQueueSourceType.BINDER: "קלסר",
    WorkQueueSourceType.TASK: "משימה",
}

STATUS_LABELS = {
    WorkQueueSourceType.VAT_WORK_ITEM: {
        "pending_materials": "ממתין לחומרים",
        "material_received": "חומרים התקבלו",
        "data_entry_in_progress": "בהקלדה",
        "ready_for_review": "מוכן לבדיקה",
        "filed": "הוגש",
        "canceled": "בוטל",
    },
    WorkQueueSourceType.ANNUAL_REPORT: {
        "not_started": "טרם התחיל",
        "collecting_docs": "איסוף מסמכים",
        "in_preparation": "בהכנה",
        "pending_client": "ממתין ללקוח",
        "submitted": "הוגש",
        "closed": "סגור",
        "canceled": "בוטל",
    },
    WorkQueueSourceType.ADVANCE_PAYMENT: {
        "pending": "ממתינה",
        "partial": "שולמה חלקית",
        "paid": "שולמה",
    },
    WorkQueueSourceType.CHARGE: {
        "draft": "טיוטה",
        "issued": "הונפק",
        "paid": "שולם",
        "canceled": "בוטל",
    },
    WorkQueueSourceType.BINDER: {
        "in_office": "במשרד",
        "ready_for_handover": "מוכן למסירה",
        "handed_over": "נמסר ללקוח",
    },
    WorkQueueSourceType.TASK: {
        "open": "פתוחה",
        "done": "הושלמה",
        "canceled": "בוטלה",
    },
}


class ClientWorkQueueProfile(NamedTuple):
    name: str
    office_number: int | None


def urgency(due_date: date, today: date) -> WorkQueueUrgency:
    days = (due_date - today).days
    if days < 0:
        return WorkQueueUrgency.OVERDUE
    if days <= APPROACHING_DAYS:
        return WorkQueueUrgency.APPROACHING
    if days <= IMPORTANT_DAYS:
        return WorkQueueUrgency.IMPORTANT
    return WorkQueueUrgency.UPCOMING


def source_key(source_type: WorkQueueSourceType, source_id: int) -> tuple[str, int]:
    return (source_type.value, source_id)


def display_status_label(source_type: WorkQueueSourceType, status: str | None) -> str | None:
    if status is None:
        return None
    return STATUS_LABELS.get(source_type, {}).get(status, status)


def load_client_profiles(
    db: Session, client_record_ids: Iterable[int]
) -> dict[int, ClientWorkQueueProfile]:
    """Fetch dashboard identity fields only for the client ids present in the result set."""
    return {
        client_id: ClientWorkQueueProfile(
            name=profile.client_name,
            office_number=profile.office_client_number,
        )
        for client_id, profile in ClientIdentityRepository(db)
        .get_display_map(client_record_ids)
        .items()
    }


class WorkQueueContext:
    def __init__(self, db: Session, today: date, *, resolve_client_identity: bool = True):
        self.db = db
        self.today = today
        self.resolve_client_identity = resolve_client_identity
        self._client_profiles: dict[int, ClientWorkQueueProfile] | None = None
        self._pending_ids: set[int] = set()

    def register_client_id(self, client_record_id: int) -> None:
        """Collect a client id for lazy batch name resolution."""
        if not self.resolve_client_identity:
            return
        self._pending_ids.add(client_record_id)

    def preload_client_identities(self, client_record_ids: Iterable[int]) -> None:
        """Register all visible clients before row serialization resolves names."""
        if not self.resolve_client_identity:
            return
        for client_record_id in client_record_ids:
            self.register_client_id(client_record_id)
        self._resolve_profiles()

    def _resolve_profiles(self) -> dict[int, ClientWorkQueueProfile]:
        missing = self._pending_ids - set(self._client_profiles or {})
        if missing:
            new_profiles = load_client_profiles(self.db, missing)
            if self._client_profiles is None:
                self._client_profiles = new_profiles
            else:
                self._client_profiles.update(new_profiles)
        elif self._client_profiles is None:
            self._client_profiles = {}
        return self._client_profiles

    def item(
        self,
        source_type: WorkQueueSourceType,
        source_id: int,
        title: str,
        due_date: date,
        client_record_id: int | None,
        *,
        business_id: int | None = None,
        item_urgency: WorkQueueUrgency | None = None,
        status_label: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> WorkQueueItem:
        if client_record_id is not None:
            self.register_client_id(client_record_id)
        client_profile = (
            self._resolve_profiles().get(client_record_id) if client_record_id is not None else None
        )
        return WorkQueueItem(
            id=f"{source_type.value}:{source_id}",
            source_type=source_type,
            source_id=source_id,
            title=title,
            description=description,
            type_label=SOURCE_TYPE_LABELS.get(source_type, source_type.value),
            status_label=display_status_label(source_type, status_label),
            due_date=due_date,
            urgency=item_urgency or urgency(due_date, self.today),
            client_record_id=client_record_id,
            client_name=client_profile.name if client_profile else None,
            office_client_number=(client_profile.office_number if client_profile else None),
            business_id=business_id,
            source_summary=WorkQueueSourceSummary(
                source_type=source_type.value,
                source_id=source_id,
                label=title,
                route=source_route(source_type, source_id),
            ),
            metadata=metadata,
        )

    def attach_client_identity(self, item: WorkQueueItem, client_record_id: int | None) -> None:
        """Populate client identity fields on an item whose client was derived later."""
        item.client_record_id = client_record_id
        if client_record_id is None:
            item.client_name = None
            item.office_client_number = None
            return
        self.register_client_id(client_record_id)
        profile = self._resolve_profiles().get(client_record_id)
        item.client_name = profile.name if profile else None
        item.office_client_number = profile.office_number if profile else None
