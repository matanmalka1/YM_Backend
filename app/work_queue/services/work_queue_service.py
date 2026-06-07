from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.tasks.models.task import TaskStatus
from app.tasks.repositories.task_repository import TaskRepository
from app.utils.time_utils import israel_today
from app.work_queue.schemas.work_queue import (
    LinkedTaskSummary,
    WorkQueueItem,
    WorkQueueLinkedFilter,
    WorkQueueListResponse,
    WorkQueueScope,
    WorkQueueSourceSummary,
    WorkQueueSourceType,
    WorkQueueSummary,
    WorkQueueUrgency,
    WorkQueueWarning,
)
from app.work_queue.services.actions import source_actions, task_actions
from app.work_queue.services.billing_items import advance_payment_items, charge_items
from app.work_queue.services.binder_items import binder_items
from app.work_queue.services.common import (
    WorkQueueContext,
    normalize_source_domain,
    source_key,
    urgency,
)
from app.work_queue.services.source_lookup import load_source_states
from app.work_queue.services.task_items import task_item, task_summary
from app.work_queue.services.tax_items import annual_report_items, vat_work_item_items

_FAR_FUTURE = date(9999, 12, 31)
_URGENCY_SORT = {
    WorkQueueUrgency.OVERDUE: 0,
    WorkQueueUrgency.APPROACHING: 1,
    WorkQueueUrgency.IMPORTANT: 2,
    WorkQueueUrgency.UPCOMING: 3,
}
_PRIORITY_SORT = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
_TASK_STATUS_SORT = {"open": 0}
_HISTORY_TASK_STATUSES = {TaskStatus.DONE.value, TaskStatus.CANCELED.value}
_ACTIVE_TASK_STATUSES = {TaskStatus.OPEN.value}


@dataclass(frozen=True)
class WorkQueueFilters:
    search: str | None = None
    source_type: WorkQueueSourceType | None = None
    urgency: WorkQueueUrgency | None = None
    urgencies: list[WorkQueueUrgency] | None = None
    task_status: TaskStatus | None = None
    linked: WorkQueueLinkedFilter | None = None
    scope: WorkQueueScope | None = None


def _task_status(item: WorkQueueItem) -> str | None:
    if item.source_type != WorkQueueSourceType.TASK or not item.metadata:
        return None
    status = item.metadata.get("status")
    return str(status) if status is not None else None


def _is_history_task_row(item: WorkQueueItem) -> bool:
    return item.source_type == WorkQueueSourceType.TASK and (
        _task_status(item) in _HISTORY_TASK_STATUSES
    )


def _is_active_task_row(item: WorkQueueItem) -> bool:
    return item.source_type == WorkQueueSourceType.TASK and (
        _task_status(item) in _ACTIVE_TASK_STATUSES
    )


def _search_text(item: WorkQueueItem) -> str:
    metadata = item.metadata or {}
    values = [
        item.title,
        item.description,
        item.client_name,
        item.office_client_number,
        item.business_id,
        item.type_label,
        item.status_label,
        item.source_type.value,
        item.source_summary.label if item.source_summary else None,
        metadata.get("business_name"),
        metadata.get("period"),
        metadata.get("period_label"),
        metadata.get("tax_year"),
        metadata.get("status"),
        metadata.get("priority"),
        metadata.get("assigned_role"),
    ]
    for task in item.linked_tasks:
        values.extend(
            [
                task.title,
                task.status,
                task.priority,
                task.assigned_role,
                task.assigned_user_id,
            ]
        )
    return " ".join(str(value).casefold() for value in values if value is not None)


def apply_work_queue_filters(
    items: list[WorkQueueItem],
    filters: WorkQueueFilters,
) -> list[WorkQueueItem]:
    filtered = items
    if filters.urgencies is not None:
        urgency_set = set(filters.urgencies)
        filtered = [item for item in filtered if item.urgency in urgency_set]
    query = filters.search.strip().casefold() if filters.search else ""
    if query:
        filtered = [item for item in filtered if query in _search_text(item)]
    if filters.source_type is not None:
        filtered = [item for item in filtered if item.source_type == filters.source_type]
    if filters.urgency is not None:
        filtered = [item for item in filtered if item.urgency == filters.urgency]
    if filters.task_status is not None:
        status_value = filters.task_status.value
        filtered = [
            item
            for item in filtered
            if _task_status(item) == status_value
            or any(task.status == status_value for task in item.linked_tasks)
        ]
    if filters.linked == WorkQueueLinkedFilter.LINKED:
        filtered = [item for item in filtered if item.linked_tasks_count > 0]
    elif filters.linked == WorkQueueLinkedFilter.UNLINKED:
        filtered = [item for item in filtered if item.linked_tasks_count == 0]
    if filters.scope == WorkQueueScope.MANUAL:
        filtered = [item for item in filtered if item.source_type == WorkQueueSourceType.TASK]
    elif filters.scope == WorkQueueScope.SYSTEM:
        filtered = [item for item in filtered if item.source_type != WorkQueueSourceType.TASK]
    return filtered


def build_work_queue_summary(items: list[WorkQueueItem]) -> WorkQueueSummary:
    by_source_type = {source_type: 0 for source_type in WorkQueueSourceType}
    by_task_status = {status.value: 0 for status in TaskStatus}
    for item in items:
        by_source_type[item.source_type] += 1
        status = _task_status(item)
        if status in by_task_status:
            by_task_status[status] += 1
        for task in item.linked_tasks:
            if task.status in by_task_status:
                by_task_status[task.status] += 1

    return WorkQueueSummary(
        total=len(items),
        manual_tasks=by_source_type[WorkQueueSourceType.TASK],
        linked=sum(1 for item in items if item.linked_tasks_count > 0),
        unlinked=sum(1 for item in items if item.linked_tasks_count == 0),
        overdue=sum(1 for item in items if item.urgency == WorkQueueUrgency.OVERDUE),
        approaching=sum(1 for item in items if item.urgency == WorkQueueUrgency.APPROACHING),
        important=sum(1 for item in items if item.urgency == WorkQueueUrgency.IMPORTANT),
        upcoming=sum(1 for item in items if item.urgency == WorkQueueUrgency.UPCOMING),
        by_source_type=by_source_type,
        by_task_status=by_task_status,
    )


class WorkQueueService:
    def __init__(self, db: Session):
        self.db = db
        self.today = israel_today()
        self.task_repo = TaskRepository(self.db)

    def _context(self, *, include_client_identity: bool = True) -> WorkQueueContext:
        return WorkQueueContext(
            self.db,
            self.today,
            resolve_client_identity=include_client_identity,
        )

    def list_items(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
        exclude_source_types: list[WorkQueueSourceType] | None = None,
        include_task_history: bool = False,
        search: str | None = None,
        source_type: WorkQueueSourceType | None = None,
        urgency: WorkQueueUrgency | None = None,
        urgencies: list[WorkQueueUrgency] | None = None,
        task_status: TaskStatus | None = None,
        linked: WorkQueueLinkedFilter | None = None,
        scope: WorkQueueScope | None = None,
        page: int = 1,
        page_size: int = 50,
        include_client_identity: bool = True,
    ) -> list[WorkQueueItem]:
        ctx = self._context(include_client_identity=include_client_identity)
        items = self._filtered_items(
            ctx,
            client_record_id=client_record_id,
            business_id=business_id,
            exclude_source_types=exclude_source_types,
            include_task_history=include_task_history,
            filters=WorkQueueFilters(
                search=search,
                source_type=source_type,
                urgency=urgency,
                urgencies=urgencies,
                task_status=task_status,
                linked=linked,
                scope=scope,
            ),
        )
        items.sort(key=self._sort_key)
        offset = (page - 1) * page_size
        return items[offset : offset + page_size]

    def list_items_with_total(
        self,
        client_record_id: int | None = None,
        business_id: int | None = None,
        exclude_source_types: list[WorkQueueSourceType] | None = None,
        include_task_history: bool = False,
        search: str | None = None,
        source_type: WorkQueueSourceType | None = None,
        urgency: WorkQueueUrgency | None = None,
        task_status: TaskStatus | None = None,
        linked: WorkQueueLinkedFilter | None = None,
        scope: WorkQueueScope | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> WorkQueueListResponse:
        ctx = self._context()
        all_items = self._filtered_items(
            ctx,
            client_record_id=client_record_id,
            business_id=business_id,
            exclude_source_types=exclude_source_types,
            include_task_history=include_task_history,
            filters=WorkQueueFilters(
                search=search,
                source_type=source_type,
                urgency=urgency,
                task_status=task_status,
                linked=linked,
                scope=scope,
            ),
        )
        all_items.sort(key=self._sort_key)
        offset = (page - 1) * page_size
        return WorkQueueListResponse(
            items=all_items[offset : offset + page_size],
            total=len(all_items),
            page=page,
            page_size=page_size,
            # Summary intentionally reflects the full filtered set before pagination.
            summary=build_work_queue_summary(all_items),
        )

    def _filtered_items(
        self,
        ctx: WorkQueueContext,
        *,
        client_record_id: int | None,
        business_id: int | None,
        exclude_source_types: list[WorkQueueSourceType] | None,
        include_task_history: bool,
        filters: WorkQueueFilters,
    ) -> list[WorkQueueItem]:
        items = self._build_items(
            ctx,
            client_record_id=client_record_id,
            business_id=business_id,
            exclude_source_types=exclude_source_types,
            include_task_history=include_task_history,
        )
        items = self._apply_mode(items, include_task_history=include_task_history)
        return apply_work_queue_filters(items, filters)

    def _build_items(
        self,
        ctx: WorkQueueContext,
        *,
        client_record_id: int | None,
        business_id: int | None,
        exclude_source_types: list[WorkQueueSourceType] | None,
        include_task_history: bool,
    ) -> list[WorkQueueItem]:
        excluded = set(exclude_source_types or [])
        system_items: list[WorkQueueItem] = []

        # VAT, annual reports, and advance payments are client-level obligations —
        # business_id does not narrow them; skip entirely when business_id is set.
        if business_id is None:
            if WorkQueueSourceType.VAT_WORK_ITEM not in excluded:
                system_items.extend(vat_work_item_items(ctx, client_record_id))
            if WorkQueueSourceType.ANNUAL_REPORT not in excluded:
                system_items.extend(annual_report_items(ctx, client_record_id))
            if WorkQueueSourceType.ADVANCE_PAYMENT not in excluded:
                system_items.extend(advance_payment_items(ctx, client_record_id))

        if WorkQueueSourceType.CHARGE not in excluded:
            system_items.extend(charge_items(ctx, client_record_id, business_id))

        # Stale binders are not client-scoped in the current query surface; include
        # when no client/business filter is active.
        if client_record_id is None and business_id is None:
            if WorkQueueSourceType.BINDER not in excluded:
                system_items.extend(binder_items(ctx))

        for item in system_items:
            item.available_actions = source_actions(
                item.source_type,
                item.source_id,
            )

        items = self._merge_tasks(
            ctx,
            system_items,
            excluded=excluded,
            client_record_id=client_record_id,
            business_id=business_id,
            include_task_history=include_task_history,
        )
        return items

    def _apply_mode(
        self, items: list[WorkQueueItem], *, include_task_history: bool
    ) -> list[WorkQueueItem]:
        if include_task_history:
            return [
                item
                for item in items
                if item.source_type != WorkQueueSourceType.TASK or _is_history_task_row(item)
            ]
        return [
            item
            for item in items
            if item.source_type != WorkQueueSourceType.TASK or _is_active_task_row(item)
        ]

    def _merge_tasks(
        self,
        ctx: WorkQueueContext,
        system_items: list[WorkQueueItem],
        *,
        excluded: set[WorkQueueSourceType],
        client_record_id: int | None,
        business_id: int | None,
        include_task_history: bool,
    ) -> list[WorkQueueItem]:
        if WorkQueueSourceType.TASK in excluded:
            return system_items

        system_by_key = {
            source_key(item.source_type, item.source_id): item for item in system_items
        }
        tasks = self.task_repo.list_for_work_queue(include_history=include_task_history)
        linked_keys = {
            (source_type, task.source_id)
            for task in tasks
            if task.source_id is not None
            for source_type in [normalize_source_domain(task.source_domain)]
            if source_type is not None
        }
        source_states = load_source_states(ctx.db, linked_keys)
        rows = list(system_items)

        for task in tasks:
            source_type = normalize_source_domain(task.source_domain)
            task_source_id = task.source_id
            should_merge = task.status == TaskStatus.OPEN
            if source_type is not None and task_source_id is not None:
                key = source_key(source_type, task_source_id)
                source_item = system_by_key.get(key)
                if source_item is not None and should_merge:
                    self._attach_task(source_item, task_summary(task))
                    continue

            standalone = task_item(ctx, task)
            if source_type is not None and task_source_id is not None:
                state = source_states.get((source_type.value, task_source_id))
                if state is not None and client_record_id is not None:
                    if state.client_record_id != client_record_id:
                        continue
                if state is not None:
                    ctx.attach_client_identity(standalone, state.client_record_id)
                    standalone.source_summary = WorkQueueSourceSummary(
                        source_type=source_type.value,
                        source_id=task_source_id,
                        label=state.label,
                        route=state.route if not state.is_missing else None,
                    )
                    if state.is_missing or state.is_deleted:
                        standalone.warnings.append(
                            WorkQueueWarning(
                                key="source_missing",
                                label="הפריט המקושר לא נמצא או נמחק",
                                severity="warning",
                            )
                        )
                    elif state.is_final:
                        standalone.warnings.append(
                            WorkQueueWarning(
                                key="source_final",
                                label="הפריט המקושר כבר טופל",
                                severity="info",
                            )
                        )
                else:
                    standalone.warnings.append(
                        WorkQueueWarning(
                            key="source_unknown",
                            label="סוג הקישור של המשימה אינו מוכר",
                            severity="warning",
                        )
                    )
            elif task.source_domain:
                standalone.warnings.append(
                    WorkQueueWarning(
                        key="source_unknown",
                        label="סוג הקישור של המשימה אינו מוכר",
                        severity="warning",
                    )
                )

            # Standalone task rows have no business scope — skip when business_id filter is active.
            if business_id is not None:
                continue
            if client_record_id is None:
                rows.append(standalone)
            elif standalone.client_record_id == client_record_id:
                rows.append(standalone)

        return rows

    def _attach_task(self, item: WorkQueueItem, task: LinkedTaskSummary) -> None:
        item.linked_tasks.append(task)
        item.linked_tasks_count = len(item.linked_tasks)
        if item.linked_tasks_count > 1:
            item.warnings = [
                warning for warning in item.warnings if warning.key != "multiple_linked_tasks"
            ]
            item.warnings.append(
                WorkQueueWarning(
                    key="multiple_linked_tasks",
                    label=f"כבר קיימות {item.linked_tasks_count} משימות קשורות",
                    severity="info",
                )
            )
        existing_endpoints = {action.endpoint for action in item.available_actions}
        existing_keys = {action.key for action in item.available_actions}
        task_row_actions = task_actions(
            task.id,
            task.status,
            key_suffix=True,
            include_delete=False,
            label_context=task.title if item.linked_tasks_count > 1 else None,
        )
        if item.linked_tasks_count == 1 and task_row_actions:
            first, *rest = task_row_actions
            item.available_actions = [first, *item.available_actions]
            existing_endpoints.add(first.endpoint)
            existing_keys.add(first.key)
            task_row_actions = rest
        for action in task_row_actions:
            if action.endpoint is None:
                if action.key in existing_keys:
                    continue
                item.available_actions.append(action)
                existing_keys.add(action.key)
                continue
            if action.endpoint not in existing_endpoints:
                item.available_actions.append(action)
                existing_endpoints.add(action.endpoint)
                existing_keys.add(action.key)
        if item.linked_tasks_count > 1:
            self._label_linked_task_actions(item)
        if task.due_date is not None:
            task_urgency = urgency(task.due_date, self.today)
            if _URGENCY_SORT[task_urgency] < _URGENCY_SORT[item.urgency]:
                item.urgency = task_urgency
                item.due_date = task.due_date

    def _label_linked_task_actions(self, item: WorkQueueItem) -> None:
        title_by_id = {task.id: task.title for task in item.linked_tasks}
        base_labels = {
            "continue_task": "פתח משימה",
            "edit_task": "ערוך משימה",
            "complete_task": "סמן כהושלמה",
            "cancel_task": "בטל משימה",
            "delete_task": "מחק משימה",
        }
        for action in item.available_actions:
            if action.task_id not in title_by_id:
                continue
            for prefix, label in base_labels.items():
                if action.key.startswith(f"{prefix}_"):
                    action.label = f"{label}: {title_by_id[action.task_id]}"
                    break

    def _sort_key(self, item: WorkQueueItem):
        task_status = None
        priority = None
        if item.source_type == WorkQueueSourceType.TASK and item.metadata:
            task_status = item.metadata.get("status")
            priority = item.metadata.get("priority")
        elif item.linked_tasks:
            task_status = item.linked_tasks[0].status
            priority = item.linked_tasks[0].priority
        item_kind = 0 if item.source_type == WorkQueueSourceType.TASK else 1
        return (
            _URGENCY_SORT.get(item.urgency, 99),
            item.due_date if item.due_date is not None else _FAR_FUTURE,
            item_kind,
            _TASK_STATUS_SORT.get(str(task_status), 9),
            _PRIORITY_SORT.get(str(priority), 9),
            item.title,
            item.source_type.value,
            item.source_id,
            item.id,
        )
